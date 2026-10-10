"""Disposable repository tests; GitHub API responses are supplied locally."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/inspect-repository.ps1'
GIT = shutil.which('git')
PWSH = shutil.which('pwsh')


@unittest.skipUnless(GIT and PWSH, 'Git and PowerShell 7 required')
class RepositoryContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='generic-repository-context-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Not an authorization source')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('remote', 'add', 'origin', 'https://github.com/acme/project-one.git')

    def git(self, *arguments, cwd=None):
        result = subprocess.run([GIT, *arguments], cwd=cwd or self.root, env=self.env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def config(self, value, root=None):
        path = (root or self.root) / '.agents/git-workflow.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def inspect(self, *arguments, responses=None, success=True):
        quoted = "'" + str(SCRIPT).replace("'", "''") + "'"
        command = """
function gh {
    $responses = $env:WORKFLOW_TEST_RESPONSES | ConvertFrom-Json -AsHashtable
    $endpoint = $args[-1]
    if (-not $responses.Contains($endpoint)) { $global:LASTEXITCODE = 1; return 'verification failed' }
    $global:LASTEXITCODE = 0
    $responses[$endpoint] | ConvertTo-Json -Depth 10
}
& """ + quoted + ' ' + ' '.join(arguments)
        result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-Command', command], cwd=self.root,
                                env=dict(self.env, WORKFLOW_TEST_RESPONSES=json.dumps(responses or {})), capture_output=True, text=True, encoding='utf-8', timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def repo(self, admin=False, **extra):
        return dict(full_name='acme/project-one', fork=False, private=False, permissions=dict(admin=admin), **extra)

    def test_local_inspection_does_not_need_authentication(self):
        context = self.inspect()
        self.assertEqual(context['candidate_repository'], 'acme/project-one')
        self.assertFalse(context['upstream_repository'])
        self.assertNotIn('login', context)

    def test_owner_uses_authenticated_login_and_direct_main(self):
        self.config(dict(upstreamRepository='acme/project-one'))
        context = self.inspect('-InspectIdentity', responses={'user': {'login': 'ACME'}})
        self.assertEqual(context['route'], 'direct-main')

    def test_verified_admin_uses_direct_main(self):
        self.config(dict(upstreamRepository='acme/project-one'))
        context = self.inspect('-InspectIdentity', responses={'user': {'login': 'maintainer'}, 'repos/acme/project-one': self.repo(admin=True)})
        self.assertEqual(context['route'], 'direct-main')

    def test_write_access_does_not_grant_direct_main(self):
        self.config(dict(upstreamRepository='acme/project-one'))
        metadata = self.repo()
        metadata['permissions'].update(push=True, maintain=True)
        context = self.inspect('-InspectIdentity', responses={'user': {'login': 'collaborator'}, 'repos/acme/project-one': metadata})
        self.assertEqual(context['route'], 'fork-pr')

    def test_string_admin_value_is_not_permission_evidence(self):
        self.config(dict(upstreamRepository='acme/project-one'))
        context = self.inspect('-InspectIdentity', responses={'user': {'login': 'collaborator'}, 'repos/acme/project-one': self.repo(admin='true')})
        self.assertEqual(context['route'], 'fork-pr')

    def test_fork_origin_resolves_source_and_existing_upstream(self):
        self.git('remote', 'set-url', 'origin', 'git@github.com:collaborator/project-one.git')
        self.git('remote', 'add', 'source', 'ssh://git@github.com/acme/project-one.git')
        context = self.inspect('-ResolveUpstream', responses={'repos/collaborator/project-one': {'full_name': 'collaborator/project-one', 'fork': True, 'source': {'full_name': 'acme/project-one'}}})
        self.assertEqual(context['upstream_repository'], 'acme/project-one')
        self.assertEqual(context['upstream_remote'], 'source')

    def test_fork_without_upstream_reports_missing_remote_without_mutation(self):
        self.git('remote', 'set-url', 'origin', 'https://github.com/collaborator/project-one.git')
        context = self.inspect('-ResolveUpstream', responses={'repos/collaborator/project-one': {'full_name': 'collaborator/project-one', 'fork': True, 'source': {'full_name': 'acme/project-one'}}})
        self.assertFalse(context['upstream_remote'])
        self.assertEqual(self.git('remote'), 'origin')

    def test_other_repo_works_without_skill_edits(self):
        self.git('remote', 'set-url', 'origin', 'https://github.com/different-team/second-project.git')
        context = self.inspect('-ResolveUpstream', responses={'repos/different-team/second-project': {'full_name': 'different-team/second-project', 'fork': False}})
        self.assertEqual(context['upstream_repository'], 'different-team/second-project')
        self.assertEqual(context['upstream_remote'], 'origin')

    def test_failed_permission_query_never_grants_direct_submission(self):
        self.config(dict(upstreamRepository='acme/project-one'))
        self.inspect('-InspectIdentity', responses={'user': {'login': 'maintainer'}}, success=False)

    def test_wrong_repository_api_response_is_rejected(self):
        self.inspect('-ResolveUpstream', responses={'repos/acme/project-one': {'full_name': 'other/unrelated', 'fork': False}}, success=False)

    def test_direct_route_rejects_mismatched_push_url(self):
        self.config(dict(upstreamRepository='acme/project-one'))
        self.git('config', 'remote.origin.pushurl', 'https://github.com/other/unrelated.git')
        self.inspect('-InspectIdentity', responses={'user': {'login': 'acme'}}, success=False)

    def test_direct_route_rejects_multiple_push_urls(self):
        self.config(dict(upstreamRepository='acme/project-one'))
        self.git('config', '--add', 'remote.origin.pushurl', 'https://github.com/acme/project-one.git')
        self.git('config', '--add', 'remote.origin.pushurl', 'https://github.com/other/unrelated.git')
        self.inspect('-InspectIdentity', responses={'user': {'login': 'acme'}}, success=False)

    def test_private_upstream_blocks_nonadmin_fork_route(self):
        self.config(dict(upstreamRepository='acme/project-one'))
        metadata = self.repo()
        metadata['private'] = True
        self.inspect('-InspectIdentity', responses={'user': {'login': 'collaborator'}, 'repos/acme/project-one': metadata}, success=False)

    def test_repo_local_routing_selects_independent_nested_repository(self):
        nested = self.root / 'arbitrary-layout/code'
        nested.mkdir(parents=True)
        self.git('init', '-b', 'main', cwd=nested)
        self.git('remote', 'add', 'origin', 'https://github.com/another-owner/nested-code.git', cwd=nested)
        self.config(dict(repositoryPath='arbitrary-layout/code'))
        self.config(dict(upstreamRepository='another-owner/nested-code'), root=nested)
        context = self.inspect()
        self.assertEqual(Path(context['root']).resolve(), nested.resolve())
        self.assertEqual(context['upstream_repository'], 'another-owner/nested-code')

    def test_routing_does_not_fall_back_to_parent_git_repository(self):
        nested = self.root / 'not-a-checkout'
        nested.mkdir()
        self.config(dict(repositoryPath='not-a-checkout'))
        self.inspect(success=False)

    def test_configuration_rejects_protected_path_outside_repository(self):
        self.config(dict(protectedPaths=['../outside']))
        self.inspect(success=False)


if __name__ == '__main__':
    unittest.main()

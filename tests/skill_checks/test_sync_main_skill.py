"""Real Git integration tests; only fetch transport is redirected to a local bare repo.

Run: python -m unittest discover -s tests/skill_checks -p test_sync_main_skill.py -v
No network, live database, production Git writes, or GitHub writes are used.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / ".agents/skills/sync-main/scripts/sync-main.ps1"
ORIGIN = "https://github.com/cjzymail-Mc/SSRC-Monday-com.git"
GIT = shutil.which("git")
PWSH = shutil.which("pwsh")


@unittest.skipUnless(GIT and PWSH, "Git and PowerShell 7 required")
class SyncMainIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flowboard-sync-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "coworker"
        self.work = self.root / "checkout"
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
        self.git(self.root, "init", "--bare", "-b", "main", str(self.remote))
        self.git(self.root, "init", "-b", "main", str(self.seed))
        self.identity(self.seed)
        self.put(self.seed, "app.txt", "first\nmiddle\nlast\n")
        self.put(self.seed, "upstream.txt", "old\n")
        self.put(self.seed, ".gitignore", "flowboard.db\nbackups/\n.env\ncache/\n")
        self.commit(self.seed, "initial")
        self.git(self.seed, "remote", "add", "origin", str(self.remote))
        self.git(self.seed, "push", "origin", "main")
        self.git(self.root, "clone", "--local", str(self.remote), str(self.work))
        self.identity(self.work)
        self.git(self.work, "remote", "set-url", "origin", ORIGIN)
        self.original = self.git(self.work, "rev-parse", "HEAD").stdout.strip()

    def git(self, cwd, *args, check=True):
        result = subprocess.run([GIT, *args], cwd=cwd, env=self.env, text=True,
                                encoding="utf-8", capture_output=True)
        if check and result.returncode:
            raise AssertionError(f"git {args}: {result.stdout}{result.stderr}")
        return result

    def identity(self, cwd):
        self.git(cwd, "config", "user.name", "Isolated test")
        self.git(cwd, "config", "user.email", "test@example.invalid")
        self.git(cwd, "config", "core.autocrlf", "false")

    def put(self, cwd, name, content):
        path = cwd / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))

    def commit(self, cwd, message):
        self.git(cwd, "add", "--all")  # Disposable fixture only.
        self.git(cwd, "commit", "-m", message)

    def advance(self, name="upstream.txt", content="coworker update\n"):
        self.put(self.seed, name, content)
        self.commit(self.seed, "coworker update")
        self.git(self.seed, "push", "origin", "main")
        return self.git(self.seed, "rev-parse", "HEAD").stdout.strip()

    def sync(self, *args, expected=0, fail_fetch=False, fetch_count=None):
        # Origin validation and all Git operations are real. This function changes
        # transport only for fetch; it does not mock merges, stashes or their exits.
        command = """
function git {
    if ($args[0] -eq 'fetch') {
        [System.IO.File]::AppendAllText($env:SYNC_TEST_FETCH_LOG, "fetch`n")
        & $env:SYNC_TEST_GIT fetch --prune $env:SYNC_TEST_REMOTE '+refs/heads/*:refs/remotes/origin/*'
    } else {
        & $env:SYNC_TEST_GIT @args
    }
    $global:LASTEXITCODE = $LASTEXITCODE
}
& """ + "'" + str(SCRIPT).replace("'", "''") + "' "
        command += " ".join("'" + arg.replace("'", "''") + "'" for arg in args)
        # Switch tokens must be parsed as parameters, not quoted positional strings.
        for switch in ("-RequireClean", "-CompleteRecovery", "-RecoverySnapshot", "-ValidateOriginOnly", "-FetchedMainCommit"):
            command = command.replace("'" + switch + "'", switch)
        command += "; exit $LASTEXITCODE"
        fetch_log = self.root / "fetch.log"
        calls_before = fetch_log.read_text().count("fetch") if fetch_log.exists() else 0
        env = dict(self.env, SYNC_TEST_GIT=GIT, SYNC_TEST_FETCH_LOG=str(fetch_log),
                   SYNC_TEST_REMOTE=str(self.root / "missing.git" if fail_fetch else self.remote))
        result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
                                cwd=self.work, env=env, text=True, encoding="utf-8",
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        if fetch_count is not None:
            calls_after = fetch_log.read_text().count("fetch") if fetch_log.exists() else 0
            self.assertEqual(calls_after - calls_before, fetch_count, result.stdout)
        return result

    def status(self):
        return self.git(self.work, "status", "--porcelain=v1", "-uall").stdout

    def journal(self):
        return json.loads((self.work / ".git/flowboard-sync-main.json").read_text(encoding="utf-8-sig"))

    def assert_current(self, oid):
        self.assertEqual(self.git(self.work, "branch", "--show-current").stdout.strip(), "main")
        self.assertEqual(self.git(self.work, "rev-parse", "HEAD").stdout.strip(), oid)

    def test_clean_fast_forward(self):
        target = self.advance()
        result = self.sync("-RequireClean")
        self.assertIn("SYNC_MAIN_OK", result.stdout)
        self.assertIn("mode=clean", result.stdout)
        self.assertIn("commits_received=1", result.stdout)
        self.assert_current(target)
        self.assertEqual(self.status(), "")

    def test_creates_missing_main_from_clean_branch(self):
        self.git(self.work, "switch", "-c", "fix/old")
        self.git(self.work, "branch", "-d", "main")
        target = self.advance()
        self.sync()
        self.assert_current(target)

    def test_dirty_staging_binary_untracked_and_existing_stash_survive(self):
        self.put(self.work, "old.txt", "older stash\n")
        self.git(self.work, "stash", "push", "-u", "-m", "keep old backup")
        old_stash = self.git(self.work, "rev-parse", "refs/stash").stdout.strip()
        self.put(self.work, "app.txt", "staged\nmiddle\nlast\n")
        self.git(self.work, "add", "app.txt")
        self.put(self.work, "app.txt", "staged\nmiddle\nunstaged\n")
        self.put(self.work, "新 文件[1].bin", b"\x00\xff\x01unfinished")
        self.put(self.work, "flowboard.db", b"runtime sentinel")
        before_index = self.git(self.work, "show", ":app.txt").stdout
        target = self.advance()
        result = self.sync()
        self.assertIn("SYNC_MAIN_WIP_OK", result.stdout)
        self.assertIn("mode=wip", result.stdout)
        self.assert_current(target)
        self.assertEqual(self.git(self.work, "show", ":app.txt").stdout, before_index)
        self.assertEqual((self.work / "app.txt").read_text(), "staged\nmiddle\nunstaged\n")
        self.assertEqual((self.work / "新 文件[1].bin").read_bytes(), b"\x00\xff\x01unfinished")
        self.assertEqual((self.work / "flowboard.db").read_bytes(), b"runtime sentinel")
        self.assertIn(old_stash, self.git(self.work, "stash", "list", "--format=%H").stdout)
        self.assertFalse((self.work / ".git/flowboard-sync-main.json").exists())
        self.assertIn("refs/sync-main/", self.git(self.work, "for-each-ref", "--format=%(refname)").stdout)
        self.assertEqual(self.git(self.work, "rev-list", "--count", "origin/main..main").stdout.strip(), "0")

    def test_no_remote_change_does_not_stash(self):
        self.put(self.work, "app.txt", "unfinished\n")
        result = self.sync(fetch_count=1)
        self.assertIn("SYNC_MAIN_WIP_OK", result.stdout)
        self.assertIn("mode=unchanged", result.stdout)
        self.assertEqual(self.git(self.work, "stash", "list").stdout, "")
        self.assertEqual((self.work / "app.txt").read_text(), "unfinished\n")

    def test_clean_no_update_fast_path(self):
        result = self.sync(fetch_count=1)
        self.assertIn("SYNC_MAIN_OK", result.stdout)
        self.assertIn("mode=unchanged", result.stdout)
        self.assertEqual(self.status(), "")
        self.assertEqual(self.git(self.work, "stash", "list").stdout, "")

    def test_clean_return_reuses_exact_fetched_base_without_network(self):
        self.git(self.work, "switch", "-c", "fix/submitted")
        target = self.advance()
        self.git(self.work, "fetch", str(self.remote), "+refs/heads/main:refs/remotes/origin/main")
        result = self.sync("-RequireClean", "-FetchedMainCommit", target, fail_fetch=True, fetch_count=0)
        self.assert_current(target)
        self.assertEqual(self.status(), "")
        self.assertIn("fetch_reused=True", result.stdout)

    def test_fetch_reuse_rejects_dirty_checkout_without_stashing(self):
        self.put(self.work, "app.txt", "unfinished\n")
        self.sync("-RequireClean", "-FetchedMainCommit", self.original, expected=10, fetch_count=0)
        self.assertEqual(self.git(self.work, "stash", "list").stdout, "")
        self.assertEqual((self.work / "app.txt").read_text(), "unfinished\n")

    def test_fetch_reuse_rejects_changed_or_unbound_base(self):
        target = self.advance()
        self.git(self.work, "fetch", str(self.remote), "+refs/heads/main:refs/remotes/origin/main")
        self.sync("-RequireClean", "-FetchedMainCommit", self.original, expected=17, fetch_count=0)
        self.assert_current(self.original)
        self.sync("-FetchedMainCommit", target, expected=17, fetch_count=0)
        self.assert_current(self.original)

    def test_rename_deletion_and_partial_staging_survive(self):
        self.git(self.work, "mv", "app.txt", "renamed file.txt")
        self.put(self.work, "renamed file.txt", "first\nmiddle\nlocal edit\n")
        (self.work / "upstream.txt").unlink()
        before_status = self.status()
        before_index = self.git(self.work, "show", ":renamed file.txt").stdout
        target = self.advance("coworker.txt", "new upstream file\n")
        self.sync()
        self.assert_current(target)
        self.assertEqual(self.status(), before_status)
        self.assertEqual(self.git(self.work, "show", ":renamed file.txt").stdout, before_index)
        self.assertFalse((self.work / "upstream.txt").exists())
        self.assertFalse((self.work / "app.txt").exists())
        self.assertIn("local edit", (self.work / "renamed file.txt").read_text())

    def test_unrelated_unmerged_index_rejected_without_new_stash(self):
        self.put(self.work, "app.txt", "local repair\n")
        self.git(self.work, "stash", "push", "-m", "other operation")
        snapshot = self.git(self.work, "rev-parse", "refs/stash").stdout.strip()
        self.advance("app.txt", "upstream repair\n")
        self.sync("-RequireClean")
        self.git(self.work, "stash", "apply", snapshot, check=False)
        self.assertIn("UU app.txt", self.status())
        self.sync(expected=12)
        self.assertEqual(self.git(self.work, "rev-parse", "refs/stash").stdout.strip(), snapshot)
        self.assertFalse((self.work / ".git/flowboard-sync-main.json").exists())

    def test_require_clean_rejects_before_fetch(self):
        self.put(self.work, "app.txt", "unfinished\n")
        self.advance()
        self.sync("-RequireClean", expected=10)
        self.assertEqual(self.git(self.work, "rev-parse", "origin/main").stdout.strip(), self.original)
        self.assertEqual((self.work / "app.txt").read_text(), "unfinished\n")

    def test_wrong_origin_rejected_without_mutation(self):
        self.git(self.work, "remote", "set-url", "origin", "https://github.com/elsewhere/repo.git")
        self.sync(expected=15)
        self.assert_current(self.original)

    def test_dirty_non_main_rejected(self):
        self.git(self.work, "switch", "-c", "fix/unfinished")
        self.put(self.work, "app.txt", "unfinished\n")
        self.sync(expected=10)
        self.assertEqual((self.work / "app.txt").read_text(), "unfinished\n")

    def test_local_commits_and_remote_divergence_preserved(self):
        self.put(self.work, "app.txt", "local committed repair\n")
        self.commit(self.work, "local")
        local = self.git(self.work, "rev-parse", "HEAD").stdout.strip()
        self.advance()
        self.put(self.work, "more.txt", "unfinished\n")
        self.sync(expected=11)
        self.assert_current(local)
        self.assertEqual((self.work / "more.txt").read_text(), "unfinished\n")

    def test_unignored_sensitive_path_rejected(self):
        self.put(self.work, "nested/.env.secret", "do not snapshot\n")
        self.advance()
        self.sync(expected=16)
        self.assert_current(self.original)
        self.assertEqual(self.git(self.work, "stash", "list").stdout, "")

    def test_incoming_guarded_file_rejected(self):
        self.put(self.seed, "flowboard.db", "fake incoming database")
        self.git(self.seed, "add", "-f", "flowboard.db")
        self.git(self.seed, "commit", "-m", "bad incoming fixture")
        self.git(self.seed, "push", "origin", "main")
        self.put(self.work, "flowboard.db", "live sentinel")
        self.put(self.work, "app.txt", "unfinished\n")
        self.sync(expected=16)
        self.assert_current(self.original)
        self.assertEqual((self.work / "flowboard.db").read_text(), "live sentinel")
        self.assertEqual(self.git(self.work, "stash", "list").stdout, "")

    def test_fetch_failure_leaves_work_in_place(self):
        self.put(self.work, "app.txt", "unfinished\n")
        self.sync(fail_fetch=True, expected=1)
        self.assertEqual((self.work / "app.txt").read_text(), "unfinished\n")
        self.assertEqual(self.git(self.work, "stash", "list").stdout, "")

    def test_conflict_resume_requires_actual_resolution(self):
        self.put(self.work, "app.txt", "local repair\nmiddle\nlast\n")
        target = self.advance("app.txt", "upstream repair\nmiddle\nlast\n")
        self.sync(expected=20)
        recovery = self.journal()
        snapshot = recovery["snapshot"]
        self.assert_current(target)
        self.assertIn("UU app.txt", self.status())
        self.sync(expected=20)  # No second stash of conflicted work.
        self.sync("-CompleteRecovery", "-RecoverySnapshot", snapshot, expected=20)
        self.put(self.work, "app.txt", "upstream repair + local repair\nmiddle\nlast\n")
        self.git(self.work, "add", "app.txt")
        self.git(self.work, "restore", "--staged", "--", "app.txt")
        self.sync("-CompleteRecovery", "-RecoverySnapshot", "wrong-oid", expected=20)
        result = self.sync("-CompleteRecovery", "-RecoverySnapshot", snapshot)
        self.assertIn("SYNC_MAIN_WIP_OK", result.stdout)
        self.assertIn(" M app.txt", self.status())
        self.assertIn("local repair", self.git(self.work, "show", f"{snapshot}:app.txt").stdout)
        self.assertEqual(self.git(self.work, "rev-parse", recovery["snapshotRef"]).stdout.strip(), snapshot)

    def test_staged_conflict_can_be_resolved_without_index_apply(self):
        self.put(self.work, "app.txt", "local repair\nmiddle\nlast\n")
        self.git(self.work, "add", "app.txt")
        self.advance("app.txt", "upstream repair\nmiddle\nlast\n")
        self.sync(expected=20)
        snapshot = self.journal()["snapshot"]
        self.assertEqual(self.status(), "")  # --index failed before restoring anything.
        self.git(self.work, "stash", "apply", snapshot, check=False)
        self.assertIn("UU app.txt", self.status())
        self.put(self.work, "app.txt", "combined upstream + local repair\nmiddle\nlast\n")
        self.git(self.work, "add", "app.txt")
        self.sync("-CompleteRecovery", "-RecoverySnapshot", snapshot)
        self.assertIn("M  app.txt", self.status())

    def test_background_fetch_during_recovery_does_not_invalidate_restoration(self):
        self.put(self.work, "app.txt", "local repair\n")
        integrated = self.advance("app.txt", "upstream repair\n")
        self.sync(expected=20)
        snapshot = self.journal()["snapshot"]
        newest = self.advance(content="coworker kept working\n")
        self.git(self.work, "fetch", str(self.remote), "+refs/heads/main:refs/remotes/origin/main")
        self.put(self.work, "app.txt", "upstream repair + local repair\n")
        self.git(self.work, "add", "app.txt")
        result = self.sync("-CompleteRecovery", "-RecoverySnapshot", snapshot)
        self.assertIn("remote_reference_changed=True", result.stdout)
        self.assertIn(f"remote_commit={integrated}", result.stdout)
        self.assertIn(f"observed_remote_commit={newest}", result.stdout)
        self.assert_current(integrated)
        self.sync()
        self.assert_current(newest)
        self.assertIn("local repair", (self.work / "app.txt").read_text())

    def test_untracked_collision_both_contents_retained_and_reconciled(self):
        self.put(self.work, "new.txt", "local new feature\n")
        self.advance("new.txt", "upstream new feature\n")
        self.sync(expected=20)
        snapshot = self.journal()["snapshot"]
        self.assertEqual((self.work / "new.txt").read_text(), "upstream new feature\n")
        self.assertEqual(self.git(self.work, "show", f"{snapshot}^3:new.txt").stdout, "local new feature\n")
        self.put(self.work, "new.txt", "upstream new feature\nlocal new feature\n")
        self.sync("-CompleteRecovery", "-RecoverySnapshot", snapshot)

    def test_repeated_remote_advances_keep_unfinished_work(self):
        self.put(self.work, "app.txt", "unfinished repair\n")
        for number in range(3):
            target = self.advance(content=f"coworker batch {number}\n")
            self.sync()
            self.assert_current(target)
            self.assertEqual((self.work / "app.txt").read_text(), "unfinished repair\n")
        self.assertEqual(len(self.git(self.work, "stash", "list").stdout.splitlines()), 3)

    def test_ignored_collision_is_not_overwritten_on_fast_forward(self):
        self.put(self.work, "cache/data.txt", "machine local\n")
        self.put(self.work, "app.txt", "unfinished\n")
        self.put(self.seed, "cache/data.txt", "incoming\n")
        self.git(self.seed, "add", "-f", "cache/data.txt")
        self.git(self.seed, "commit", "-m", "incoming cache fixture")
        self.git(self.seed, "push", "origin", "main")
        self.sync(expected=21)
        self.assert_current(self.original)
        self.assertEqual((self.work / "cache/data.txt").read_text(), "machine local\n")
        self.assertEqual(self.journal()["phase"], "saved")
        self.assertIn("unfinished", self.git(self.work, "show", f"{self.journal()['snapshot']}:app.txt").stdout)


if __name__ == "__main__":
    unittest.main()

import json
import base64
import http.client
import io
import zipfile
import shutil
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

import flowboard.database as database
from flowboard.database import SCHEMA_VERSION, connect, migrate
from flowboard.timeline import TimelineService
from flowboard.transfer import make_xlsx, parse_upload
from server import create_server
from test_secure_foundation import create_legacy_database


class TimelineCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flowboard-timeline-")
        self.db = Path(self.temp.name) / "flowboard.db"
        migrate(self.db, initial_password="test-password")
        self.service = TimelineService(self.db)
        self.admin = {"id": "u1"}

    def tearDown(self):
        self.temp.cleanup()

    def _create_with_nodes(self, name, nodes):
        project_id = self.service.create_project(self.admin, 1, {"name": name})["project_id"]
        return project_id, self.service.submit_batches(self.admin, 1, {"requests": [{
            "project_id": project_id, "base_version": 1,
            "changes": [{"create": node} for node in nodes],
        }]})["results"][0]

    def test_v16_migration_five_tables_and_checks(self):
        db = connect(self.db)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes", "timeline_import_batches"} <= tables)
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=16").fetchone()[0], 1)
        db.close()

    def test_project_create_then_batch_nodes_and_derived_view(self):
        project_id, result = self._create_with_nodes("新品发布", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-05"},
            {"track": "parallel", "stage": "测试", "name": "兼容", "date": "2026-08-10"},
        ])
        view = self.service.get_project(self.admin, project_id)
        self.assertEqual(view["metrics"]["start_date"], "2026-08-01")
        self.assertEqual((len(view["nodes"]), len(view["segments"]), len(view["stage_intervals"])), (3, 3, 3))
        self.assertEqual([node["interval_days"] for node in view["nodes"]], [None, 4, None])
        db = connect(self.db)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_change_batches").fetchone()[0], 1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_node_changes").fetchone()[0], 3)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_log WHERE action_code='timeline.batch_committed'").fetchone()[0], 1)
        db.close()

    def test_name_conflict_and_viewer_denied(self):
        self.service.create_project(self.admin, 1, {"name": "独家项目"})
        db = connect(self.db)
        db.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'")
        db.commit()
        db.close()
        with self.assertRaises(Exception) as conflict:
            self.service.create_project(self.admin, 1, {"name": "独家项目"})
        self.assertEqual(conflict.exception.status, 422)
        with self.assertRaises(Exception) as viewer:
            self.service.list_projects({"id": "u2"}, 1)
        self.assertEqual(viewer.exception.status, 403)

    def _member(self):
        return {"id": "u3"}

    def _create_as_member(self, name):
        db = connect(self.db)
        db.execute("INSERT INTO users VALUES ('u2','u2','成员','test-password',NULL,NULL,1,'2026-01-01T00:00:00+00:00')")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','member')")
        db.execute("INSERT INTO users VALUES ('u3','u3','其他成员','test-password',NULL,NULL,1,'2026-01-01T00:00:00+00:00')")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u3','member')")
        db.commit(); db.close()
        member = {"id": "u2"}
        return member, self.service.create_project(member, 1, {"name": name})["project_id"]

    def _snapshot_counts(self):
        db = connect(self.db)
        values = tuple(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
            "timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes", "audit_log"
        ))
        db.close()
        return values

    def _raw_state(self, project_id):
        db = connect(self.db)
        try:
            return {
                "project": tuple(db.execute("SELECT version,deleted_at FROM timeline_projects WHERE id=?", (project_id,)).fetchone()),
                "nodes": [tuple(row) for row in db.execute("SELECT id,date,done_at,updated_at FROM timeline_nodes WHERE project_id=? ORDER BY id", (project_id,))],
            }
        finally:
            db.close()

    def test_group1_project_permissions_and_lifecycle(self):
        owner, project_id = self._create_as_member("他人项目")
        other = self._member()
        with self.assertRaises(Exception) as mismatch:
            self.service.submit_batches(owner, 999, {"requests": [{"project_id": project_id, "base_version": 1, "changes": [{"create": {"track": "main", "stage": "创意", "name": "错空间", "date": "2026-08-01"}}]}]})
        self.assertEqual(mismatch.exception.status, 403)
        with self.assertRaises(Exception) as caught:
            self.service.submit_batches(other, 1, {"requests": [{"project_id": project_id, "base_version": 1, "changes": [{"create": {"track": "main", "stage": "创意", "name": "越权", "date": "2026-08-01"}}]}]})
        self.assertEqual(caught.exception.status, 403)
        self.service.get_project(owner, project_id)
        with self.assertRaises(Exception) as injected:
            self.service.submit_batches(owner, 1, {"requests": [{"project_id": project_id, "base_version": 1, "changes": [{"node_id": 999999, "set": {"name": "注入"}}]}]})
        self.assertEqual(injected.exception.status, 422)

        db = connect(self.db)
        db.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'")
        db.commit(); db.close()
        viewer = {"id": "u2"}
        with self.assertRaises(Exception) as viewer_read:
            self.service.get_project(viewer, project_id)
        self.assertEqual(viewer_read.exception.status, 403)
        with self.assertRaises(Exception) as viewer_create:
            self.service.create_project(viewer, 1, {"name": "只读项目"})
        self.assertEqual(viewer_create.exception.status, 403)

        db = connect(self.db)
        db.execute("UPDATE workspace_memberships SET role='member' WHERE user_id='u2'")
        db.commit(); db.close()
        with self.assertRaises(Exception) as member_delete:
            self.service.delete_project(owner, 1, project_id, {"base_version": 1})
        self.assertEqual(member_delete.exception.status, 403)
        deleted = self.service.delete_project(self.admin, 1, project_id, {"base_version": 1})
        self.assertEqual(deleted["version"], 2)
        for operation in (
            lambda: self.service.get_project(owner, project_id),
            lambda: self.service.submit_batches(owner, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"create": {"track": "main", "stage": "创意", "name": "后删", "date": "2026-08-01"}}]}]}),
            lambda: self.service.delete_project(self.admin, 1, project_id, {"base_version": 2}),
        ):
            with self.assertRaises(Exception) as inactive:
                operation()
            self.assertEqual(inactive.exception.status, 404)
        db = connect(self.db)
        self.assertIsNotNone(db.execute("SELECT deleted_at FROM timeline_projects WHERE id=?", (project_id,)).fetchone()[0])
        db.close()

    def test_group2_initial_date_lock_and_group3_conflict_views(self):
        project_id, created = self._create_with_nodes("锁字段", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-04"},
        ])
        first_id, second_id = [node["id"] for node in created["view"]["nodes"]]
        with self.assertRaises(Exception) as unknown:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": first_id, "set": {"initial_date": "2026-07-01"}}]}]})
        self.assertEqual(unknown.exception.status, 422)
        member = self._member()
        with self.assertRaises(Exception) as denied:
            self.service.initial_correction(member, 1, {"project_id": project_id, "base_version": 2, "corrections": [{"node_id": first_id, "initial_date": "2026-07-01"}, {"node_id": second_id, "initial_date": "2026-07-04"}]})
        self.assertEqual(denied.exception.status, 403)
        corrected = self.service.initial_correction(self.admin, 1, {"project_id": project_id, "base_version": 2, "corrections": [{"node_id": first_id, "initial_date": "2026-07-01"}, {"node_id": second_id, "initial_date": "2026-07-04"}]})
        self.assertEqual(corrected["results"][0]["version"], 3)
        with self.assertRaises(Exception) as duplicate:
            self.service.initial_correction(self.admin, 1, {"project_id": project_id, "base_version": 3, "corrections": [{"node_id": first_id, "initial_date": "2026-07-01"}, {"node_id": first_id, "initial_date": "2026-07-02"}]})
        self.assertEqual(duplicate.exception.status, 422)
        before = self._snapshot_counts()
        with self.assertRaises(Exception) as version:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 999, "changes": [{"node_id": first_id, "set": {"date": "2026-08-20"}}]}]})
        self.assertEqual(version.exception.status, 409)
        conflict = version.exception.details
        view = next(item["view"] for item in conflict["conflicts"] if item["project_id"] == project_id)
        self.assertTrue(all(key in view for key in ("nodes", "segments", "stage_intervals", "metrics")))
        self.assertEqual(self._snapshot_counts(), before)

    def test_group3_missing_versions_and_exact_zero_writes(self):
        project_id, created = self._create_with_nodes("缺版本", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-04"},
        ])
        first_id = created["view"]["nodes"][0]["id"]
        before = self._raw_state(project_id)
        with self.assertRaises(Exception) as correction_missing:
            self.service.initial_correction(self.admin, 1, {"project_id": project_id, "corrections": [{"node_id": first_id, "initial_date": "2026-07-01"}]})
        self.assertEqual(correction_missing.exception.status, 428)
        with self.assertRaises(Exception) as delete_missing:
            self.service.delete_project(self.admin, 1, project_id, {})
        self.assertEqual(delete_missing.exception.status, 428)
        self.assertEqual(self._raw_state(project_id), before)

        batch_before = self._snapshot_counts()
        with self.assertRaises(Exception) as full_batch_conflict:
            self.service.submit_batches(self.admin, 1, {"requests": [
                {"project_id": project_id, "base_version": 999, "changes": [{"node_id": first_id, "set": {"date": "2026-09-01"}}]},
                {"project_id": project_id, "base_version": 999, "changes": [{"node_id": first_id, "set": {"done_at": True}}]},
            ]})
        self.assertEqual(full_batch_conflict.exception.status, 409)
        self.assertEqual(self._snapshot_counts(), batch_before)

    def test_group4_undo_guards(self):
        project_id, created = self._create_with_nodes("撤销项目", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-04"},
        ])
        first_id, second_id = [node["id"] for node in created["view"]["nodes"]]
        with self.assertRaises(Exception) as missing:
            self.service.undo_batches(self.admin, 1, {"batch_ids": [404]})
        self.assertEqual(missing.exception.status, 404)
        first_update = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": first_id, "set": {"date": "2026-08-02"}}]}]})["results"][0]
        second_update = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 3, "changes": [{"node_id": second_id, "set": {"done_at": True}}]}]})["results"][0]
        before = self._snapshot_counts()
        with self.assertRaises(Exception) as stale:
            self.service.undo_batches(self.admin, 1, {"batch_ids": [first_update["batch_id"]]})
        self.assertEqual(stale.exception.status, 409)
        self.assertEqual(self._snapshot_counts(), before)
        undo = self.service.undo_batches(self.admin, 1, {"batch_ids": [second_update["batch_id"]]})["results"][0]
        self.assertFalse(self.service.get_project(self.admin, project_id)["nodes"][1]["done_at"])
        with self.assertRaises(Exception) as undo_undo:
            self.service.undo_batches(self.admin, 1, {"batch_ids": [undo["batch_id"]]})
        self.assertEqual(undo_undo.exception.status, 409)

    def test_group12_empty_and_project_unique_contract(self):
        project_id = self.service.create_project(self.admin, 1, {"name": "唯一项目"})["project_id"]
        with self.assertRaises(Exception) as empty:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 1, "changes": []}]})
        self.assertEqual(empty.exception.status, 422)
        with self.assertRaises(Exception) as correction_empty:
            self.service.initial_correction(self.admin, 1, {"project_id": project_id, "base_version": 1, "corrections": []})
        self.assertEqual(correction_empty.exception.status, 422)
        before = self._snapshot_counts()
        with self.assertRaises(Exception) as duplicate:
            self.service.create_project(self.admin, 1, {"name": "唯一项目"})
        self.assertEqual(duplicate.exception.status, 422)
        self.assertEqual(self._snapshot_counts()[0], before[0])

    def test_batch_update_conflict_noop_and_cascade(self):
        project_id, created = self._create_with_nodes("版本项目", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-05"},
            {"track": "main", "stage": "开发", "name": "联调", "date": "2026-08-08"},
        ])
        first_id, second_id, third_id = [node["id"] for node in created["view"]["nodes"]]
        no_op = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": second_id, "set": {"date": "2026-08-05"}}]}]})
        self.assertTrue(no_op["results"][0]["no_op"])
        updated = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "details": {"mode": "cascade"}, "changes": [{"node_id": second_id, "set": {"date": "2026-08-08", "done_at": True}}]}]})
        self.assertEqual(updated["results"][0]["version"], 3)
        dates = {node["id"]: node["date"] for node in updated["results"][0]["view"]["nodes"]}
        self.assertEqual((dates[first_id], dates[second_id], dates[third_id]), ("2026-08-01", "2026-08-08", "2026-08-11"))
        before = self.service.get_project(self.admin, project_id)
        with self.assertRaises(Exception) as conflict:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": second_id, "set": {"date": "2026-08-20"}}]}]})
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(self.service.get_project(self.admin, project_id), before)

    def test_group5_mixed_batch_audit_kinds(self):
        project_id, created = self._create_with_nodes("混合批次", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-05"},
        ])
        first_id, second_id = [node["id"] for node in created["view"]["nodes"]]
        mixed = self.service.submit_batches(self.admin, 1, {"requests": [{
            "project_id": project_id, "base_version": 2,
            "changes": [
                {"node_id": first_id, "set": {"date": "2026-08-02"}},
                {"node_id": second_id, "set": {"done_at": True}},
            ],
        }]})["results"][0]
        db = connect(self.db)
        try:
            batch = db.execute("SELECT change_kind,details_json FROM timeline_change_batches WHERE id=?", (mixed["batch_id"],)).fetchone()
            self.assertEqual(batch["change_kind"], "direct_edit")
            self.assertEqual(json.loads(batch["details_json"])["kinds"], ["direct_edit", "status_toggle"])
            rows = [tuple(row) for row in db.execute("SELECT field,change_role FROM timeline_node_changes WHERE batch_id=? ORDER BY id", (mixed["batch_id"],))]
            self.assertEqual(rows, [("date", "direct"), ("date", "cascaded"), ("done_at", "direct")])
        finally:
            db.close()

    def test_cascade_anchors_status_only_and_date_priority(self):
        project_id, created = self._create_with_nodes("多锚点项目", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-05"},
            {"track": "main", "stage": "开发", "name": "联调", "date": "2026-08-08"},
            {"track": "main", "stage": "测试", "name": "验收", "date": "2026-08-12"},
            {"track": "main", "stage": "量产", "name": "发布", "date": "2026-08-15"},
        ])
        first_id, second_id, third_id, fourth_id, fifth_id = [node["id"] for node in created["view"]["nodes"]]
        updated = self.service.submit_batches(self.admin, 1, {"requests": [{
            "project_id": project_id,
            "base_version": 2,
            "details": {"mode": "cascade"},
            "changes": [
                {"node_id": second_id, "set": {"interval_days": 99}},
                {"node_id": second_id, "set": {"date": "2026-08-08"}},
                {"node_id": third_id, "set": {"done_at": True}},
                {"node_id": fourth_id, "set": {"date": "2026-08-14"}},
            ],
        }]})["results"][0]
        dates = {node["id"]: node["date"] for node in updated["view"]["nodes"]}
        self.assertEqual(
            (dates[first_id], dates[second_id], dates[third_id], dates[fourth_id], dates[fifth_id]),
            ("2026-08-01", "2026-08-08", "2026-08-11", "2026-08-14", "2026-08-17"),
        )
        db = connect(self.db)
        rows = db.execute(
            """SELECT c.node_id,c.change_role,c.field FROM timeline_node_changes c
               WHERE c.batch_id=? ORDER BY c.node_id,c.id""",
            (updated["batch_id"],),
        ).fetchall()
        rows = [tuple(row) for row in rows]
        self.assertIn((third_id, "cascaded", "date"), tuple(rows))
        self.assertIn((third_id, "direct", "done_at"), tuple(rows))
        self.assertIn((fifth_id, "cascaded", "date"), tuple(rows))
        db.close()

    def test_single_and_cascade_clamping(self):
        single_id, single_created = self._create_with_nodes("单节点钳制", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-05"},
            {"track": "main", "stage": "开发", "name": "联调", "date": "2026-08-08"},
        ])
        cascade_id, cascade_created = self._create_with_nodes("顺延钳制", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-05"},
            {"track": "main", "stage": "开发", "name": "联调", "date": "2026-08-08"},
        ])
        single_second = single_created["view"]["nodes"][1]["id"]
        cascade_second = cascade_created["view"]["nodes"][1]["id"]
        results = self.service.submit_batches(self.admin, 1, {"requests": [
            {"project_id": single_id, "base_version": 2, "details": {"mode": "single"}, "changes": [{"node_id": single_second, "set": {"date": "2026-08-20"}}]},
            {"project_id": cascade_id, "base_version": 2, "details": {"mode": "cascade"}, "changes": [{"node_id": cascade_second, "set": {"date": "2026-07-01"}}]},
        ]})["results"]
        single_dates = tuple(node["date"] for node in results[0]["view"]["nodes"])
        cascade_dates = tuple(node["date"] for node in results[1]["view"]["nodes"])
        self.assertEqual(single_dates, ("2026-08-01", "2026-08-08", "2026-08-11"))
        self.assertEqual(cascade_dates, ("2026-08-01", "2026-08-01", "2026-08-04"))

    def test_group6_write_chain_rules_and_snapshot_neighbor(self):
        project_id, created = self._create_with_nodes("写入规则", [
            {"track": "main", "stage": "创意", "name": "B2", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "B10", "date": "2026-08-04"},
            {"track": "main", "stage": "开发", "name": "B1", "date": "2026-08-08"},
            {"track": "parallel", "stage": "测试", "name": "并行", "date": "2026-08-03"},
        ])
        nodes = created["view"]["nodes"]
        first_id, second_id, third_id = [node["id"] for node in nodes if node["track"] == "main"]
        parallel_id = next(node["id"] for node in nodes if node["track"] == "parallel")
        with self.assertRaises(Exception) as first_interval:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": first_id, "set": {"interval_days": 1}}]}]})
        self.assertEqual(first_interval.exception.status, 422)
        with self.assertRaises(Exception) as create_interval:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"create": {"track": "main", "stage": "测试", "name": "新", "date": "2026-08-10", "interval_days": 2}}]}]})
        self.assertEqual(create_interval.exception.status, 422)
        with self.assertRaises(Exception) as track_and_interval:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": parallel_id, "set": {"track": "main", "interval_days": 2}}]}]})
        self.assertEqual(track_and_interval.exception.status, 422)
        with self.assertRaises(Exception) as boolean_done:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": parallel_id, "set": {"done_at": "yes"}}]}]})
        self.assertEqual(boolean_done.exception.status, 422)

        interval_update = self.service.submit_batches(self.admin, 1, {"requests": [{
            "project_id": project_id, "base_version": 2,
            "changes": [{"node_id": third_id, "set": {"interval_days": 6}}],
        }]})["results"][0]
        by_id = {node["id"]: node for node in interval_update["view"]["nodes"]}
        self.assertEqual(by_id[third_id]["interval_days"], 6)
        self.assertEqual(by_id[third_id]["date"], "2026-08-10")
        self.assertEqual(by_id[parallel_id]["interval_days"], None)
        self.assertEqual([node["name"] for node in interval_update["view"]["nodes"] if node["track"] == "main"], ["B2", "B10", "B1"])

    def test_initial_correction_undo_and_review(self):
        project_id, created = self._create_with_nodes("复盘项目", [{"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"}])
        node_id = created["view"]["nodes"][0]["id"]
        corrected = self.service.initial_correction(self.admin, 1, {"project_id": project_id, "base_version": 2, "corrections": [{"node_id": node_id, "initial_date": "2026-07-25"}]})
        self.assertEqual(corrected["results"][0]["version"], 3)
        review = self.service.review(self.admin, 1, [project_id])
        self.assertEqual(review["projects"][0]["summary"]["direct_edit_total"], 0)
        self.assertEqual(review["projects"][0]["nodes"][0]["delta_days"], 7)
        undo = self.service.undo_batches(self.admin, 1, {"batch_ids": [corrected["results"][0]["batch_id"]]})
        self.assertEqual(undo["results"][0]["version"], 4)
        self.assertEqual(self.service.get_project(self.admin, project_id)["nodes"][0]["initial_date"], "2026-08-01")

    def test_group7_view_metrics_review_pagination_and_undo_count(self):
        project_id, created = self._create_with_nodes("视图矩阵", [
            {"track": "main", "stage": "创意", "name": "概念", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "方案", "date": "2026-08-05"},
            {"track": "parallel", "stage": "量产", "name": "并行", "date": "2026-08-03"},
        ])
        first_id = created["view"]["nodes"][0]["id"]
        second_id = next(node["id"] for node in created["view"]["nodes"] if node["track"] == "main" and node["stage"] == "设计")
        parallel_id = next(node["id"] for node in created["view"]["nodes"] if node["track"] == "parallel")
        view = self.service.get_project(self.admin, project_id)
        self.assertEqual(view["metrics"]["start_date"], "2026-08-01")
        self.assertEqual(view["metrics"]["current_stage"], "量产")
        self.assertEqual(view["metrics"]["upcoming"], [])
        self.assertEqual(view["metrics"]["overdue_count"], 3)
        self.assertEqual(view["metrics"]["this_week_count"], 0)
        self.assertEqual([(interval["track"], interval["stage"], interval["node_ids"], interval["row_index"]) for interval in view["stage_intervals"]], [
            ("main", "创意", [first_id], 0),
            ("main", "设计", [second_id], 0),
            ("parallel", "量产", [parallel_id], 0),
        ])

        changed = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": first_id, "set": {"date": "2026-08-02"}}]}]})["results"][0]
        for index in range(49):
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 3 + index, "changes": [{"node_id": second_id, "set": {"remark": f"批-{index}"}}]}]})
        review = self.service.review(self.admin, 1, [project_id])
        payload = review["projects"][0]
        self.assertEqual(len(payload["batches"]), 50)
        self.assertTrue(payload["has_more"])
        self.assertEqual([row["batch_id"] for row in payload["batches"]], list(range(payload["batches"][0]["batch_id"], payload["batches"][-1]["batch_id"] - 1, -1)))
        self.assertEqual(payload["nodes"][0]["direct_edit_count"], 1)

        latest_batch_id = payload["batches"][0]["batch_id"]
        undo = self.service.undo_batches(self.admin, 1, {"batch_ids": [latest_batch_id]})["results"][0]
        self.assertEqual(undo["view"]["nodes"][0]["date"], "2026-08-02")
        after_undo = self.service.review(self.admin, 1, [project_id])
        self.assertEqual(next(node for node in after_undo["projects"][0]["nodes"] if node["node_id"] == first_id)["direct_edit_count"], 1)

        viewer = {"id": "u2"}
        db = connect(self.db)
        db.execute("INSERT INTO users VALUES ('u2','u2','只读','test-password',NULL,NULL,1,'2026-01-01T00:00:00+00:00')")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','viewer')")
        db.commit(); db.close()
        with self.assertRaises(Exception) as denied:
            self.service.review(viewer, 1, [project_id])
        self.assertEqual(denied.exception.status, 403)

    def test_group8_excel_negative_controls(self):
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        with self.assertRaises(Exception) as header_mismatch:
            self.service.preview_import(self.admin, 1, "timeline.csv", "项目,错误\nA,B\n".encode())
        self.assertEqual(header_mismatch.exception.status, 422)
        self.assertEqual(header_mismatch.exception.code, "IMPORT_HEADERS_MISMATCH")

        cases = [
            ("非法日期", "日期", "08/01/2026"),
            ("非法轨道", "轨道", "unknown"),
            ("非法阶段", "阶段", "未知"),
            ("非法状态", "状态", "maybe"),
            ("非法状态旧值", "状态", "未完成"),
        ]
        for project_name, header, value in cases:
            row = ["新项目", "创意", "main", "节点", "2026-08-01", "", "未开始", ""]
            row[headers.index(header)] = value
            raw = make_xlsx(headers, [row])
            with self.assertRaises(Exception) as rejected:
                self.service.preview_import(self.admin, 1, "timeline.xlsx", raw)
            self.assertEqual(rejected.exception.status, 422)
            self.assertEqual(rejected.exception.details["row"], 2)

        source = make_xlsx(headers, [["整数日期", "创意", "main", "节点", "2026-08-01", "", "未开始", ""]])
        fractional_bytes = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(source)) as source_zip, zipfile.ZipFile(fractional_bytes, "w") as target:
            for item in source_zip.infolist():
                content = source_zip.read(item.filename)
                if item.filename == "xl/worksheets/sheet1.xml":
                    content = content.replace(b'<c r="E2" t="inlineStr"><is><t xml:space="preserve">2026-08-01</t></is></c>', b'<c r="E2"><v>46234.5</v></c>')
                target.writestr(item, content)
            fractional_serial = fractional_bytes.getvalue()
        with self.assertRaises(Exception) as serial:
            self.service.preview_import(self.admin, 1, "fractional.xlsx", fractional_serial)
        self.assertEqual(serial.exception.status, 422)

        self.service.create_project(self.admin, 1, {"name": "同名项目"})
        same_name = make_xlsx(headers, [["同名项目", "创意", "main", "节点", "2026-08-01", "", "未开始", ""]])
        with self.assertRaises(Exception) as existing_name:
            self.service.preview_import(self.admin, 1, "same.xlsx", same_name)
        self.assertEqual((existing_name.exception.status, existing_name.exception.code), (422, "NAME_CONFLICT"))
        duplicate = make_xlsx(headers, [
            ["文件重复", "创意", "main", "节点", "2026-08-01", "", "未开始", ""],
            ["文件重复", "创意", "main", "节点", "2026-08-01", "", "未开始", ""],
        ])
        with self.assertRaises(Exception) as in_file:
            self.service.preview_import(self.admin, 1, "duplicate.xlsx", duplicate)
        self.assertEqual((in_file.exception.status, in_file.exception.details["row"]), (422, 3))
        self.assertIn("与第 2 行重复", in_file.exception.message)
        db = connect(self.db)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_import_batches").fetchone()[0], 0)
        finally:
            db.close()

    def test_group9_excel_round_trip_in_new_workspace(self):
        project_a, created_a = self._create_with_nodes("往返甲项目", [
            {"track": "main", "stage": "创意", "name": "里程碑起点", "date": "2026-07-15"},
            {"track": "main", "stage": "设计", "name": "方案定稿", "date": "2026-08-20"},
            {"track": "main", "stage": "开发", "name": "联调完成", "date": "2026-09-10"},
            {"track": "parallel", "stage": "测试", "name": "兼容验证", "date": "2026-08-01"},
            {"track": "parallel", "stage": "量产", "name": "批量供货", "date": "2026-08-30"},
        ])
        project_b, _ = self._create_with_nodes("往返乙项目", [
            {"track": "main", "stage": "应用迭代", "name": "边" * 500, "date": "2026-08-05", "remark": "中文备注-跨月"},
        ])
        done_id = next(node["id"] for node in created_a["view"]["nodes"] if node["name"] == "方案定稿")
        self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_a, "base_version": 2, "changes": [{"node_id": done_id, "set": {"done_at": True}}]}]})
        source_views = [self.service.get_project(self.admin, pid) for pid in (project_a, project_b)]
        source_nodes = {(view["name"], node["name"]): node for view in source_views for node in view["nodes"]}
        self.assertEqual(len(source_nodes), 6)
        self.assertTrue(source_nodes[("往返甲项目", "方案定稿")]["done_at"])

        raw = self.service.export_timeline(self.admin, 1)
        self.assertIsInstance(raw, bytes)
        self.assertGreater(len(raw), 0)
        parsed = parse_upload("roundtrip.xlsx", raw)
        self.assertEqual(parsed["headers"], ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"])
        self.assertEqual(len(parsed["rows"]), 6)

        db = connect(self.db)
        db.execute("INSERT INTO workspaces VALUES (2,'新空间','2026-01-01T00:00:00+00:00',30)")
        db.execute("INSERT INTO workspace_memberships VALUES (2,'u1','admin')")
        db.commit(); db.close()
        preview = self.service.preview_import(self.admin, 2, "roundtrip.xlsx", raw)
        self.assertEqual(preview["row_count"], 6)
        self.assertEqual([{"name": p["name"], "node_count": p["node_count"]} for p in preview["projects"]], [
            {"name": "往返甲项目", "node_count": 5},
            {"name": "往返乙项目", "node_count": 1},
        ])
        committed = self.service.commit_import(self.admin, 2, {"batch_id": preview["batch_id"]})
        self.assertEqual((committed["projects"], committed["nodes"]), (2, 6))

        new_views = [self.service.get_project(self.admin, p["project_id"]) for p in self.service.list_projects(self.admin, 2)["projects"]]
        self.assertEqual(sorted(view["name"] for view in new_views), ["往返乙项目", "往返甲项目"])
        today = date.fromisoformat(new_views[0]["server_today"])
        for view in new_views:
            source_view = next(item for item in source_views if item["name"] == view["name"])
            self.assertEqual(sorted((n["track"], n["stage"], n["name"], n["date"], n["remark"]) for n in view["nodes"]),
                             sorted((n["track"], n["stage"], n["name"], n["date"], n["remark"]) for n in source_view["nodes"]))
            intervals = {track: [n["interval_days"] for n in view["nodes"] if n["track"] == track] for track in ("main", "parallel")}
            source_intervals = {track: [n["interval_days"] for n in source_view["nodes"] if n["track"] == track] for track in ("main", "parallel")}
            self.assertEqual(intervals, source_intervals)
            for node in view["nodes"]:
                source_node = source_nodes[(view["name"], node["name"])]
                self.assertEqual(bool(node["done_at"]), bool(source_node["done_at"]))
                if node["done_at"]:
                    self.assertEqual(node["status"], "已完成")
                else:
                    self.assertEqual(node["status"], "未开始" if date.fromisoformat(node["date"]) >= today else "进行中")
        with self.assertRaises(Exception) as same_name:
            self.service.preview_import(self.admin, 2, "again.xlsx", raw)
        self.assertEqual((same_name.exception.status, same_name.exception.code), (422, "NAME_CONFLICT"))

    def test_group10_true_v15_to_v16_migration_backup_and_idempotence(self):
        path = Path(self.temp.name) / "seeded-v15.db"
        create_legacy_database(path)
        db = connect(path)
        database._migration_v1(db, "test-password")
        for version in range(2, 16):
            getattr(database, f"_migration_v{version}")(db)
        before = {
            table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("users", "workspaces", "boards", "groups_", "tasks", "comments", "activity")
        }
        task_rows = [tuple(row) for row in db.execute("SELECT id,title,status,priority,due,owner_id,description FROM tasks ORDER BY id")]
        db.close()

        backup = migrate(path)
        self.assertTrue(backup and Path(backup).exists())
        self.assertTrue(Path(backup).name.startswith("seeded-v15-pre-v16-"))
        db = connect(path)
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            timeline_tables = {"timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes", "timeline_import_batches"}
            self.assertTrue(timeline_tables <= tables)
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 16)
            self.assertEqual({table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}, before)
            self.assertEqual([tuple(row) for row in db.execute("SELECT id,title,status,priority,due,owner_id,description FROM tasks ORDER BY id")], task_rows)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_projects").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_change_batches").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_node_changes").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_import_batches").fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(db.execute("SELECT checksum FROM schema_migrations WHERE version=16").fetchone()[0], "flowboard-schema-v16")
            migration_count = db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        finally:
            db.close()

    def test_group11_import_two_phase_race_and_replay(self):
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        raw = make_xlsx(headers, [["预览项目", "创意", "main", "概念", "2026-08-01", "999", "未开始", "导入备注"]])
        preview = self.service.preview_import(self.admin, 1, "timeline.xlsx", raw)
        db = connect(self.db)
        stored = json.loads(db.execute("SELECT preview_json FROM timeline_import_batches WHERE id=?", (preview["batch_id"],)).fetchone()[0])
        db.close()
        self.assertEqual(stored[0]["remark"], "导入备注")
        self.assertNotIn("interval", stored[0])

        self.service.create_project(self.admin, 1, {"name": "预览项目"})
        before = self._snapshot_counts()
        with self.assertRaises(Exception) as race:
            self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        self.assertEqual(race.exception.status, 422)
        self.assertEqual(self._snapshot_counts()[0], before[0])

        db = connect(self.db)
        db.execute("DELETE FROM timeline_projects WHERE name='预览项目'")
        db.commit(); db.close()
        committed = self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        imported = self.service.get_project(self.admin, next(project["project_id"] for project in self.service.list_projects(self.admin, 1)["projects"] if project["name"] == "预览项目"))
        self.assertEqual(imported["nodes"][0]["remark"], "导入备注")
        self.assertEqual(imported["nodes"][0]["date"], "2026-08-01")

        with self.assertRaises(Exception) as repeat:
            self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        self.assertEqual(repeat.exception.status, 409)
        with self.assertRaises(Exception) as missing:
            self.service.commit_import(self.admin, 1, {"batch_id": 404})
        self.assertEqual(missing.exception.status, 404)

        tampered = make_xlsx(headers, [["自由名", "创意", "main", "坏行", "2026-08-01", "", "未开始", ""]])
        tampered_preview = self.service.preview_import(self.admin, 1, "tampered.xlsx", tampered)
        self.service.create_project(self.admin, 1, {"name": "自由名"})
        db = connect(self.db)
        db.execute("UPDATE timeline_import_batches SET preview_json=? WHERE id=?", (json.dumps([{"project": "自由名", "track": "unknown", "stage": "创意", "name": "坏行", "date": "2026-08-01", "status": "未完成", "remark": ""}]), tampered_preview["batch_id"]))
        db.commit(); db.close()
        before = self._snapshot_counts()
        with self.assertRaises(Exception) as replay:
            self.service.commit_import(self.admin, 1, {"batch_id": tampered_preview["batch_id"]})
        self.assertEqual(replay.exception.status, 422)
        self.assertEqual(self._snapshot_counts(), before)

    def test_group1_unauthenticated_http_401(self):
        server = create_server("127.0.0.1", 0, self.db)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
            connection.request("GET", "/api/workspaces/1/timeline")
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            self.assertEqual(response.status, 401)
            self.assertEqual(payload["error"]["code"], "AUTH_REQUIRED")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_excel_import_preview_commit_and_export(self):
        raw = make_xlsx(["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"], [["导入项目", "创意", "main", "概念", "2026-08-01", "", "未开始", ""]])
        preview = self.service.preview_import(self.admin, 1, "timeline.xlsx", raw)
        self.assertEqual((preview["row_count"], len(preview["projects"])), (1, 1))
        committed = self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        self.assertEqual((committed["projects"], committed["nodes"]), (1, 1))
        with self.assertRaises(Exception) as repeat:
            self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        self.assertEqual(repeat.exception.status, 409)
        exported = self.service.export_timeline(self.admin, 1)
        self.assertTrue(exported)

    def test_import_headers_contract_literal(self):
        contract = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        accepted = self.service.preview_import(self.admin, 1, "contract.xlsx", make_xlsx(contract, [["表头项目", "创意", "main", "节点", "2026-08-01", "", "未开始", ""]]))
        self.assertEqual(accepted["row_count"], 1)

        for label, headers, cells in (
            ("旧表头", ["项目", "轨道", "阶段", "节点", "日期", "状态", "备注", "间隔"], ["表头项目", "main", "创意", "节点", "2026-08-01", "未开始", "", ""]),
            ("乱序", ["项目名称", "轨道", "阶段", "节点", "日期", "间隔", "状态", "备注"], ["表头项目", "创意", "main", "节点", "2026-08-01", "", "未开始", ""]),
            ("缺列", contract[:7], ["表头项目", "创意", "main", "节点", "2026-08-01", "", "未开始"]),
            ("多列", contract + ["备注二"], ["表头项目", "创意", "main", "节点", "2026-08-01", "", "未开始", "", ""]),
        ):
            with self.assertRaises(Exception) as rejected:
                self.service.preview_import(self.admin, 1, f"{label}.xlsx", make_xlsx(headers, [cells]))
            self.assertEqual((rejected.exception.status, rejected.exception.code), (422, "IMPORT_HEADERS_MISMATCH"), label)
            self.assertEqual(rejected.exception.details["headers"], contract, label)
            self.assertIn("项目名称", rejected.exception.message, label)

    def test_import_xlsx_serial_positive_and_boundaries(self):
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        expected = lambda serial: (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()
        self.assertEqual(expected(18264), "1950-01-01")
        self.assertEqual(expected(73051), "2100-01-01")
        raw = make_xlsx(headers, [
            ["序列下界", "创意", "main", "节点", 18264, "", "未开始", ""],
            ["序列中值", "创意", "main", "节点", 46234, "", "未开始", ""],
            ["序列上界", "创意", "main", "节点", 73051, "", "未开始", ""],
            ["文本日期", "创意", "main", "节点", "2026-08-01", "", "未开始", ""],
        ])
        parsed = parse_upload("serials.xlsx", raw)
        self.assertEqual(parsed["rows"][0][4], "18264")
        preview = self.service.preview_import(self.admin, 1, "serials.xlsx", raw)
        committed = self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        self.assertEqual((committed["projects"], committed["nodes"]), (4, 4))
        by_name = {view["name"]: view for view in self.service.list_projects(self.admin, 1)["projects"]}
        self.assertEqual(by_name["序列下界"]["nodes"][0]["date"], expected(18264))
        self.assertEqual(by_name["序列中值"]["nodes"][0]["date"], expected(46234))
        self.assertEqual(by_name["序列上界"]["nodes"][0]["date"], expected(73051))
        self.assertEqual(by_name["文本日期"]["nodes"][0]["date"], "2026-08-01")

        for bad in (18263, 73052, 46234.5):
            with self.assertRaises(Exception) as rejected:
                self.service.preview_import(self.admin, 1, f"bad-{bad}.xlsx", make_xlsx(headers, [["越界项目", "创意", "main", "节点", bad, "", "未开始", ""]]))
            self.assertEqual(rejected.exception.status, 422)
            self.assertEqual(rejected.exception.details["row"], 2)
        with self.assertRaises(Exception) as csv_text:
            self.service.preview_import(self.admin, 1, "serial.csv", "项目名称,阶段,轨道,节点,日期,间隔,状态,备注\n序列项目,创意,main,节点,46234,,未开始\n".encode())
        self.assertEqual(csv_text.exception.status, 422)
        self.assertEqual(csv_text.exception.details["row"], 2)

    def test_import_status_three_states_and_recompute(self):
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        raw = make_xlsx(headers, [
            ["状态项目", "创意", "main", "态一", "2026-07-01", "", "已完成", ""],
            ["状态项目", "创意", "main", "态二", "2026-07-02", "", "未开始", ""],
            ["状态项目", "创意", "main", "态三", "2026-12-01", "", "进行中", ""],
            ["状态项目", "创意", "main", "态四", "2026-12-02", "", "", ""],
            ["状态项目", "创意", "main", "态五", "2026-12-03", "", "已完成", ""],
        ])
        preview = self.service.preview_import(self.admin, 1, "status.xlsx", raw)
        self.assertEqual([p["node_count"] for p in preview["projects"]], [5])
        committed = self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        self.assertEqual((committed["projects"], committed["nodes"]), (1, 5))
        view = next(p for p in self.service.list_projects(self.admin, 1)["projects"] if p["name"] == "状态项目")
        today = date.fromisoformat(view["server_today"])
        nodes = {node["name"]: node for node in view["nodes"]}
        self.assertTrue(nodes["态一"]["done_at"])
        self.assertEqual(nodes["态一"]["status"], "已完成")
        for name in ("态二", "态三", "态四"):
            self.assertFalse(nodes[name]["done_at"], name)
            expected_status = "未开始" if date.fromisoformat(nodes[name]["date"]) >= today else "进行中"
            self.assertEqual(nodes[name]["status"], expected_status, name)
        self.assertTrue(nodes["态五"]["done_at"])
        self.assertEqual(nodes["态五"]["status"], "已完成")
        db = connect(self.db)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE done_at IS NOT NULL").fetchone()[0], 2)
        finally:
            db.close()
        with self.assertRaises(Exception) as legacy_value:
            self.service.preview_import(self.admin, 1, "legacy.xlsx", make_xlsx(headers, [["旧值项目", "创意", "main", "节点", "2026-08-01", "", "未完成", ""]]))
        self.assertEqual(legacy_value.exception.status, 422)
        self.assertEqual(legacy_value.exception.details["row"], 2)

    def test_import_multirow_aggregation_and_counts(self):
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        raw = make_xlsx(headers, [
            ["聚合项目", "创意", "main", "节点一", "2026-08-01", "", "未开始", ""],
            ["聚合项目", "测试", "parallel", "节点二", "2026-08-05", "", "进行中", ""],
            ["聚合项目", "设计", "main", "节点三", "2026-09-01", "", "", ""],
        ])
        preview = self.service.preview_import(self.admin, 1, "multirow.xlsx", raw)
        self.assertEqual(preview["row_count"], 3)
        self.assertEqual([{"name": p["name"], "node_count": p["node_count"]} for p in preview["projects"]], [{"name": "聚合项目", "node_count": 3}])
        committed = self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        self.assertEqual((committed["projects"], committed["nodes"]), (1, 3))
        db = connect(self.db)
        try:
            project_id = db.execute("SELECT id FROM timeline_projects WHERE name='聚合项目'").fetchone()[0]
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_nodes WHERE project_id=?", (project_id,)).fetchone()[0], 3)
        finally:
            db.close()

        before = self._snapshot_counts()
        with self.assertRaises(Exception) as existing:
            self.service.preview_import(self.admin, 1, "again.xlsx", raw)
        self.assertEqual((existing.exception.status, existing.exception.code), (422, "NAME_CONFLICT"))
        self.assertEqual(self._snapshot_counts()[0], before[0])
        db = connect(self.db)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_import_batches").fetchone()[0], 1)
        finally:
            db.close()

        dup = make_xlsx(headers, [
            ["重复项目", "创意", "main", "节点一", "2026-08-01", "", "未开始", ""],
            ["重复项目", "测试", "parallel", "节点二", "2026-08-05", "", "未开始", ""],
            ["重复项目", "设计", "main", "节点三", "2026-09-01", "", "未开始", ""],
            ["重复项目", "设计", "main", "节点三", "2026-09-01", "", "未开始", ""],
        ])
        with self.assertRaises(Exception) as duplicate:
            self.service.preview_import(self.admin, 1, "dup.xlsx", dup)
        self.assertEqual((duplicate.exception.status, duplicate.exception.details["row"], duplicate.exception.details["duplicate_of"]), (422, 5, 4))
        self.assertIn("与第 4 行重复", duplicate.exception.message)

        for label, rows in (
            ("同名同日不同节点", [["键项目", "创意", "main", "A", "2026-08-01", "", "", ""], ["键项目", "创意", "main", "B", "2026-08-01", "", "", ""]]),
            ("同名同节点不同日", [["键项目二", "创意", "main", "A", "2026-08-01", "", "", ""], ["键项目二", "创意", "main", "A", "2026-08-02", "", "", ""]]),
        ):
            distinct = self.service.preview_import(self.admin, 1, f"{label}.xlsx", make_xlsx(headers, rows))
            self.assertEqual((distinct["row_count"], len(distinct["projects"])), (2, 1), label)

    def test_import_field_limits_boundaries(self):
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        raw = make_xlsx(headers, [["限" * 200, "创意", "main", "节" * 500, "2026-08-01", "", "未开始", "注" * 500]])
        preview = self.service.preview_import(self.admin, 1, "limits.xlsx", raw)
        committed = self.service.commit_import(self.admin, 1, {"batch_id": preview["batch_id"]})
        self.assertEqual((committed["projects"], committed["nodes"]), (1, 1))
        view = next(p for p in self.service.list_projects(self.admin, 1)["projects"] if p["name"] == "限" * 200)
        self.assertEqual(len(view["nodes"][0]["name"]), 500)
        self.assertEqual(len(view["nodes"][0]["remark"]), 500)

        for label, row in (
            ("节点名超长", ["限名项目", "创意", "main", "节" * 501, "2026-08-01", "", "未开始", ""]),
            ("备注超长", ["限注项目", "创意", "main", "节点", "2026-08-01", "", "未开始", "注" * 501]),
            ("项目名超长", ["项" * 201, "创意", "main", "节点", "2026-08-01", "", "未开始", ""]),
        ):
            with self.assertRaises(Exception) as rejected:
                self.service.preview_import(self.admin, 1, f"{label}.xlsx", make_xlsx(headers, [row]))
            self.assertEqual(rejected.exception.status, 422)
            self.assertEqual(rejected.exception.details["row"], 2)

        project_id, created = self._create_with_nodes("接口上限项目", [{"track": "main", "stage": "创意", "name": "原节点", "date": "2026-08-01"}])
        node_id = created["view"]["nodes"][0]["id"]
        with self.assertRaises(Exception) as api_long:
            self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": node_id, "set": {"name": "批" * 501}}]}]})
        self.assertEqual(api_long.exception.status, 422)
        renamed = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": node_id, "set": {"name": "批" * 500}}]}]})
        self.assertEqual(renamed["results"][0]["view"]["nodes"][0]["name"], "批" * 500)

    def test_export_exact_1000_and_over_limit_fail_closed(self):
        for index in range(5):
            self._create_with_nodes(f"千行项目{index}", [
                {"track": "main" if position % 2 == 0 else "parallel", "stage": "创意", "name": f"N{position:04d}", "date": (date(2026, 1, 1) + timedelta(days=position % 200)).isoformat()}
                for position in range(200)
            ])
        raw = self.service.export_timeline(self.admin, 1)
        parsed = parse_upload("export.xlsx", raw)
        self.assertEqual(len(parsed["rows"]), 1000)

        db = connect(self.db)
        db.execute("INSERT INTO workspaces VALUES (2,'新空间','2026-01-01T00:00:00+00:00',30)")
        db.execute("INSERT INTO workspace_memberships VALUES (2,'u1','admin')")
        db.commit(); db.close()
        preview = self.service.preview_import(self.admin, 2, "export.xlsx", raw)
        self.assertEqual(preview["row_count"], 1000)
        self.assertEqual(sorted(preview["projects"], key=lambda item: item["name"]), sorted(({"name": f"千行项目{index}", "node_count": 200} for index in range(5)), key=lambda item: item["name"]))
        committed = self.service.commit_import(self.admin, 2, {"batch_id": preview["batch_id"]})
        self.assertEqual((committed["projects"], committed["nodes"]), (5, 1000))

        db = connect(self.db)
        project_id = db.execute("SELECT id FROM timeline_projects WHERE name='千行项目0'").fetchone()[0]
        db.execute(
            "INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (project_id, "main", "创意", "OVERFLOW", "2026-12-31", "2026-12-31", "", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        db.commit(); db.close()
        with self.assertRaises(Exception) as over_limit:
            self.service.export_timeline(self.admin, 1)
        self.assertEqual(over_limit.exception.status, 422)
        self.assertEqual(over_limit.exception.code, "EXPORT_LIMIT")
        self.assertEqual(over_limit.exception.details, {"total": 1001, "max": 1000})

    def test_group4_undo_three_batch_middle_and_reverse_roles(self):
        def full_snapshot(project_id):
            db = connect(self.db)
            try:
                return {
                    "project": tuple(db.execute("SELECT version,deleted_at FROM timeline_projects WHERE id=?", (project_id,)).fetchone()),
                    "nodes": [tuple(row) for row in db.execute("SELECT id,date,done_at,deleted_at,updated_at,version FROM timeline_nodes WHERE project_id=? ORDER BY id", (project_id,))],
                    "batches": db.execute("SELECT COUNT(*) FROM timeline_change_batches WHERE project_id=?", (project_id,)).fetchone()[0],
                    "changes": db.execute("SELECT COUNT(*) FROM timeline_node_changes WHERE batch_id IN (SELECT id FROM timeline_change_batches WHERE project_id=?)", (project_id,)).fetchone()[0],
                    "audits": db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
                }
            finally:
                db.close()

        project_id, created = self._create_with_nodes("三批撤销项目", [
            {"track": "main", "stage": "创意", "name": "首节点", "date": "2026-08-01"},
            {"track": "main", "stage": "设计", "name": "次节点", "date": "2026-08-04"},
        ])
        first_id, second_id = [node["id"] for node in created["view"]["nodes"]]
        b1 = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 2, "changes": [{"node_id": first_id, "set": {"date": "2026-08-02"}}]}]})["results"][0]["batch_id"]
        b2 = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 3, "changes": [{"node_id": second_id, "set": {"remark": "中批"}}]}]})["results"][0]["batch_id"]
        b3 = self.service.submit_batches(self.admin, 1, {"requests": [{"project_id": project_id, "base_version": 4, "changes": [
            {"create": {"track": "main", "stage": "开发", "name": "新节点", "date": "2026-08-06"}},
            {"node_id": second_id, "remove": True},
        ]}]})["results"][0]["batch_id"]
        self.assertTrue(b1 < b2 < b3)
        db = connect(self.db)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_change_batches WHERE project_id=?", (project_id,)).fetchone()[0], 4)
        finally:
            db.close()

        before = full_snapshot(project_id)
        with self.assertRaises(Exception) as middle:
            self.service.undo_batches(self.admin, 1, {"batch_ids": [b2]})
        self.assertEqual((middle.exception.status, middle.exception.code), (409, "UNDO_TARGET_STALE"))
        self.assertEqual(full_snapshot(project_id), before)

        undone = self.service.undo_batches(self.admin, 1, {"batch_ids": [b3]})["results"][0]
        self.assertEqual(undone["version"], 6)
        db = connect(self.db)
        try:
            new_row = db.execute("SELECT deleted_at FROM timeline_nodes WHERE project_id=? AND name='新节点'", (project_id,)).fetchone()
            self.assertIsNotNone(new_row)
            self.assertIsNotNone(new_row["deleted_at"])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM timeline_node_changes WHERE batch_id=?", (b3,)).fetchone()[0], 2)
            undo_row = db.execute("SELECT change_kind,undone_batch_id FROM timeline_change_batches WHERE id=?", (undone["batch_id"],)).fetchone()
            self.assertEqual((undo_row["change_kind"], undo_row["undone_batch_id"]), ("undo", b3))
        finally:
            db.close()
        view = self.service.get_project(self.admin, project_id)
        self.assertEqual([node["name"] for node in view["nodes"]], ["首节点", "次节点"])
        restored = next(node for node in view["nodes"] if node["name"] == "次节点")
        self.assertEqual(restored["remark"], "中批")
        with self.assertRaises(Exception) as undo_undo:
            self.service.undo_batches(self.admin, 1, {"batch_ids": [undone["batch_id"]]})
        self.assertEqual(undo_undo.exception.status, 409)

    def test_group10_backup_content_idempotence_rollback(self):
        path = Path(self.temp.name) / "seeded-v15-evidence.db"
        create_legacy_database(path)
        db = connect(path)
        database._migration_v1(db, "test-password")
        for version in range(2, 16):
            getattr(database, f"_migration_v{version}")(db)
        before = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("users", "workspaces", "boards", "groups_", "tasks", "comments", "activity")}
        sentinels = [tuple(row) for row in db.execute("SELECT id,title,status,priority,due,owner_id FROM tasks ORDER BY id")]
        db.close()
        self.assertGreater(len(sentinels), 0)

        backups_dir = Path(self.temp.name) / "backups"
        self.assertFalse(backups_dir.exists())
        backup = migrate(path)
        self.assertTrue(backup and Path(backup).exists() and Path(backup).stat().st_size > 0)
        self.assertIn("-pre-v16-", Path(backup).name)
        self.assertEqual(sorted(item.name for item in backups_dir.iterdir()), [Path(backup).name])

        snap = connect(backup)
        try:
            self.assertEqual(snap.execute("PRAGMA user_version").fetchone()[0], 15)
            tables = {row[0] for row in snap.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse({"timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes", "timeline_import_batches"} & tables)
            self.assertEqual({table: snap.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}, before)
            self.assertEqual([tuple(row) for row in snap.execute("SELECT id,title,status,priority,due,owner_id FROM tasks ORDER BY id")], sentinels)
        finally:
            snap.close()

        restore_dir = Path(self.temp.name) / "restore"
        restore_dir.mkdir()
        rollback = restore_dir / "rollback-restore.db"
        shutil.copy(backup, rollback)
        rb = connect(rollback)
        try:
            self.assertEqual(rb.execute("PRAGMA user_version").fetchone()[0], 15)
            self.assertEqual([tuple(row) for row in rb.execute("SELECT id,title,status,priority,due,owner_id FROM tasks ORDER BY id")], sentinels)
        finally:
            rb.close()
        migrate(rollback)
        rb = connect(rollback)
        try:
            self.assertEqual(rb.execute("PRAGMA user_version").fetchone()[0], 16)
            tables = {row[0] for row in rb.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes", "timeline_import_batches"} <= tables)
            self.assertEqual([tuple(row) for row in rb.execute("SELECT id,title,status,priority,due,owner_id FROM tasks ORDER BY id")], sentinels)
        finally:
            rb.close()

        second = migrate(path)
        self.assertIsNone(second)
        self.assertEqual(sorted(item.name for item in backups_dir.iterdir()), [Path(backup).name])
        main = connect(path)
        try:
            self.assertEqual(main.execute("PRAGMA user_version").fetchone()[0], 16)
            self.assertEqual(main.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=16").fetchone()[0], 1)
            timeline_counts = [main.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("timeline_projects", "timeline_nodes", "timeline_change_batches", "timeline_node_changes", "timeline_import_batches")]
            self.assertEqual(timeline_counts, [0, 0, 0, 0, 0])
            self.assertEqual(main.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(main.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            main.close()


if __name__ == "__main__":
    unittest.main()

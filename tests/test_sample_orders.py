import base64
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image

from flowboard.database import connect, copy_database
from flowboard.operations import create_backup, verify_backup
from server import create_server
from test_secure_foundation import create_legacy_database


class SampleOrderHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flowboard-sample-orders-")
        self.db = str(Path(self.temp.name) / "flowboard.db")
        create_legacy_database(self.db)
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        os.environ["FLOWBOARD_ATTACHMENT_DIR"] = str(Path(self.temp.name) / "blobs")
        self.server = create_server("127.0.0.1", 0, self.db)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()
        os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)
        os.environ.pop("FLOWBOARD_ATTACHMENT_DIR", None)

    def request(self, method, path, body=None, cookie=None, csrf=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        conn.request(method, path, payload, headers)
        response = conn.getresponse()
        raw = response.read()
        result = response.status, raw, dict(response.getheaders())
        conn.close()
        return result

    def login(self, username):
        status, raw, headers = self.request("POST", "/api/auth/login", {"username": username, "password": "test-password"})
        self.assertEqual(status, 200)
        return headers["Set-Cookie"], json.loads(raw)["csrf_token"]

    @staticmethod
    def order(number, count=1):
        return {"number": number, "order_date": "2026-11-06", "status": "已下单",
                "handover_status": "部分接收", "receiver": "张三", "requester": "杨祖锐",
                "department": "科技中心", "note": "", "scan_file": "",
                "items": [{"id": str(i), "style": f"ABC{i}", "category": "篮球", "contractor": "先锋",
                           "sole": "OD-123", "gender": "男", "color": "白", "quantity": i + 1,
                           "size": "42", "purpose": "测试", "due_date": "2026-11-20", "remark": "", "photo_file": ""}
                          for i in range(count)]}

    def test_shared_crud_permissions_exports_and_restore(self):
        admin, csrf = self.login("u1")
        member, member_csrf = self.login("u2")
        root = "/api/workspaces/1/sample-orders"
        self.assertEqual(self.request("GET", root)[0], 401)
        self.assertEqual(self.request("POST", root, self.order("SO-1"), admin)[0], 403)
        status, raw, _ = self.request("POST", root, self.order("SO-1"), admin, csrf)
        self.assertEqual(status, 201, raw)
        saved = json.loads(raw)
        self.assertEqual(saved["version"], 1)
        self.assertEqual(len(json.loads(self.request("GET", root, cookie=member)[1])), 1)
        self.assertEqual(self.request("POST", root, self.order("SO-1"), member, member_csrf)[0], 409)
        signed = self.request("GET", f"{root}/{saved['id']}/signed.xlsx", cookie=member)
        self.assertEqual(signed[0], 200, signed[1][:500])
        sheet = load_workbook(io.BytesIO(signed[1])).active
        self.assertEqual(sheet.max_column, 12)
        self.assertEqual(sheet.max_row, 7)
        self.assertEqual(sheet["B5"].value, "ABC0篮球")
        self.assertEqual(sheet["G5"].value, 1)
        self.assertEqual(sheet["G6"].value, 1)
        self.assertNotIn("先锋", [cell.value for row in sheet for cell in row])
        annual = self.request("GET", root + "/annual.xlsx?year=2026", cookie=member)
        self.assertEqual(annual[0], 200)
        self.assertEqual(load_workbook(io.BytesIO(annual[1]))["年度汇总"]["C2"].value, 1)
        edited = {**saved, "note": "同事已看", "version": 1}
        status, raw, _ = self.request("PUT", f"{root}/{saved['id']}", edited, member, member_csrf)
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["version"], 2)
        self.assertEqual(self.request("PUT", f"{root}/{saved['id']}", edited, admin, csrf)[0], 409)
        self.assertEqual(self.request("DELETE", f"{root}/{saved['id']}", {"version": 2}, admin, csrf)[0], 200)
        self.assertEqual(len(json.loads(self.request("GET", root, cookie=member)[1])), 0)
        trash = json.loads(self.request("GET", root + "/trash", cookie=member)[1])
        self.assertEqual(len(trash), 1)
        self.assertEqual(self.request("POST", f"{root}/{saved['id']}/restore", {"version": trash[0]["version"]}, member, member_csrf)[0], 200)

    def test_upload_template_multiple_rows_and_viewer(self):
        admin, csrf = self.login("u1")
        root = "/api/workspaces/1/sample-orders"
        image = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(image, format="PNG")
        png = image.getvalue()
        status, raw, _ = self.request("POST", root + "/upload", {"kind": "photo", "data": base64.b64encode(png).decode()}, admin, csrf)
        self.assertEqual(status, 201, raw)
        name = json.loads(raw)["file"]
        self.assertEqual(self.request("GET", root + "/files/" + name, cookie=admin)[1], png)
        package = create_backup(self.db, Path(self.temp.name) / "blobs", Path(self.temp.name) / "verified-backups", label="sample-test")
        manifest = verify_backup(package)
        self.assertIn(name, [entry["storage_name"] for entry in manifest["attachments"]])
        order = self.order("SO-3", 3)
        order["items"][0]["photo_file"] = name
        status, raw, _ = self.request("POST", root, order, admin, csrf)
        self.assertEqual(status, 201, raw)
        signed = self.request("GET", f"{root}/{json.loads(raw)['id']}/signed.xlsx", cookie=admin)
        self.assertEqual(signed[0], 200)
        sheet = load_workbook(io.BytesIO(signed[1])).active
        self.assertEqual(sheet.max_row, 9)
        self.assertEqual(sheet["B7"].value, "ABC2篮球")
        self.assertEqual(sheet["G8"].value, 6)
        self.assertEqual(len(sheet._images), 2)  # 原模板标识图 + 新上传鞋款图
        db = connect(self.db)
        db.execute("UPDATE workspace_memberships SET role='viewer' WHERE user_id='u2'")
        db.commit()
        db.close()
        viewer, viewer_csrf = self.login("u2")
        self.assertEqual(self.request("GET", root, cookie=viewer)[0], 200)
        self.assertEqual(self.request("POST", root, self.order("SO-4"), viewer, viewer_csrf)[0], 403)
        self.assertEqual(self.request("POST", root + "/upload", {"kind": "photo", "data": base64.b64encode(png).decode()}, viewer, viewer_csrf)[0], 403)

    def test_migration_backup_restores_legacy_snapshot(self):
        backups = list((Path(self.temp.name) / "backups").glob("*.db"))
        self.assertTrue(backups)
        restored = Path(self.temp.name) / "restored.db"
        copy_database(backups[0], restored)
        conn = connect(restored)
        try:
            self.assertLess(conn.execute("PRAGMA user_version").fetchone()[0], 21)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

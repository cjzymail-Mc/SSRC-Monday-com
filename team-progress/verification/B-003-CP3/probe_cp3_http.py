"""Independent CP3 acceptance probe: temp DB + OS-assigned port + real HTTP."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_timeline_http import TimelineHTTPTests, make_xlsx
from flowboard.database import connect


def expect(actual, expected, key):
    if actual != expected:
        raise AssertionError(f"{key}: expected {expected!r}, got {actual!r}")


def main():
    h = TimelineHTTPTests(methodName="runTest")
    h.setUp()
    evidence = {"port": h.port, "checks": []}
    try:
        cookie, csrf = h.login()
        viewer_cookie, viewer_csrf = h.login("u3")
        member_cookie, member_csrf = h.login("u2")
        headers = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
        preview_path = "/api/workspaces/1/timeline/imports/preview"
        commit_path = "/api/workspaces/1/timeline/imports/commit"

        good = make_xlsx(headers, [["独立旅程", "创意", "main", "N", 46234, "", "已完成", ""]])
        before = h.counts()
        cases = [
            ("preview_csrf", h.request("POST", preview_path, h.upload("good.xlsx", good), cookie=cookie), 403, "CSRF_INVALID"),
            ("preview_viewer", h.request("POST", preview_path, h.upload("good.xlsx", good), cookie=viewer_cookie, csrf=viewer_csrf), 403, "PROJECT_FORBIDDEN"),
            ("preview_base64", h.request("POST", preview_path, {"filename": "bad.xlsx", "content_base64": "%%%"}, cookie=cookie, csrf=csrf), 422, "IMPORT_FILE_INVALID"),
            ("preview_headers", h.request("POST", preview_path, h.upload("bad.xlsx", make_xlsx(["坏表头"], [["x"]])), cookie=cookie, csrf=csrf), 422, "IMPORT_HEADERS_MISMATCH"),
        ]
        for key, (status, payload, _), wanted_status, wanted_code in cases:
            expect((status, payload["error"]["code"]), (wanted_status, wanted_code), key)
            evidence["checks"].append([key, status, wanted_code])
        expect(h.counts(), before, "negative previews zero write")

        status, preview, _ = h.request("POST", preview_path, h.upload("good.xlsx", good), cookie=cookie, csrf=csrf)
        expect(status, 201, "preview success")
        status, committed, _ = h.request("POST", commit_path, {"batch_id": preview["batch_id"]}, cookie=cookie, csrf=csrf)
        expect((status, committed["projects"], committed["nodes"]), (201, 1, 1), "commit success")
        status, replay, _ = h.request("POST", commit_path, {"batch_id": preview["batch_id"]}, cookie=cookie, csrf=csrf)
        expect((status, replay["error"]["code"]), (409, "TIMELINE_IMPORT_ALREADY_COMMITTED"), "replay")

        raw = make_xlsx(headers, [["他人批次", "创意", "main", "N", "2026-08-01", "", "", ""]])
        _, own_preview, _ = h.request("POST", preview_path, h.upload("own.xlsx", raw), cookie=cookie, csrf=csrf)
        stable = h.counts()
        status, other, _ = h.request("POST", commit_path, {"batch_id": own_preview["batch_id"]}, cookie=member_cookie, csrf=member_csrf)
        expect((status, other["error"]["code"]), (404, "TIMELINE_IMPORT_BATCH_NOT_FOUND"), "other user")
        status, cross, _ = h.request("POST", "/api/workspaces/2/timeline/imports/commit", {"batch_id": own_preview["batch_id"]}, cookie=cookie, csrf=csrf)
        if status not in (403, 404):
            raise AssertionError(f"cross workspace: {status} {cross}")
        expect(h.counts(), stable, "other/cross zero write")

        demote_raw = make_xlsx(headers, [["降权零写", "创意", "main", "N", "2026-08-01", "", "", ""]])
        _, demote_preview, _ = h.request("POST", preview_path, h.upload("demote.xlsx", demote_raw), cookie=member_cookie, csrf=member_csrf)
        db = connect(h.db_path)
        db.execute("UPDATE workspace_memberships SET role='viewer' WHERE workspace_id=1 AND user_id='u2'")
        db.commit()
        db.close()
        stable = h.counts()
        status, demoted, _ = h.request("POST", commit_path, {"batch_id": demote_preview["batch_id"]}, cookie=member_cookie, csrf=member_csrf)
        expect((status, demoted["error"]["code"]), (403, "PROJECT_FORBIDDEN"), "demoted viewer")
        expect(h.counts(), stable, "demoted zero write")

        race_raw = make_xlsx(headers, [["竞态零写", "创意", "main", "N", "2026-08-01", "", "", ""]])
        _, race_preview, _ = h.request("POST", preview_path, h.upload("race.xlsx", race_raw), cookie=cookie, csrf=csrf)
        h.create_project(cookie, csrf, "竞态零写")
        stable = h.counts()
        status, race, _ = h.request("POST", commit_path, {"batch_id": race_preview["batch_id"]}, cookie=cookie, csrf=csrf)
        expect((status, race["error"]["code"]), (422, "NAME_CONFLICT"), "same-name race")
        expect(h.counts(), stable, "race zero write")

        h.create_project(cookie, csrf, "已有")
        conflict = make_xlsx(headers, [["已有", "创意", "main", "A", "2026-08-01", "", "", ""], ["新", "创意", "main", "B", "2026-08-01", "", "", ""], ["已有", "设计", "parallel", "C", "2026-08-02", "", "", ""]])
        status, err, _ = h.request("POST", preview_path, h.upload("conflict.xlsx", conflict), cookie=cookie, csrf=csrf)
        expect((status, err["error"]["code"], [r["row"] for r in err["error"]["details"]["rows"]]), (422, "NAME_CONFLICT", [2, 4]), "all conflict rows")

        multi = h.two_sheet_xlsx(headers, [["多表", "创意", "main", "N", "2026-08-01", "", "", ""]])
        status, multi_preview, _ = h.request("POST", preview_path, h.upload("multi.xlsx", multi), cookie=cookie, csrf=csrf)
        expect(status, 201, "multi sheet")
        if "仅导入第一个 sheet" not in multi_preview["warnings"]:
            raise AssertionError("multi sheet warning missing")

        typed = make_xlsx(headers, [["文本日期", "创意", "main", "N", "46234", "", "", ""], ["分数日期", "创意", "main", "N", 46234.5, "", "", ""]])
        status, typed_err, _ = h.request("POST", preview_path, h.upload("typed.xlsx", typed), cookie=cookie, csrf=csrf)
        expect((status, typed_err["error"]["code"], typed_err["error"]["details"]["row"]), (422, "VALIDATION_ERROR", 2), "xlsx text integer controlled")
        fractional = make_xlsx(headers, [["分数日期", "创意", "main", "N", 46234.5, "", "", ""]])
        status, frac_err, _ = h.request("POST", preview_path, h.upload("fractional.xlsx", fractional), cookie=cookie, csrf=csrf)
        expect((status, frac_err["error"]["code"], frac_err["error"]["details"]["row"]), (422, "VALIDATION_ERROR", 2), "xlsx fractional controlled")
        csv = "项目名称,阶段,轨道,节点,日期,间隔,状态,备注\nCSV变形,创意,main,N,46234,,,\n".encode()
        status, csv_err, _ = h.request("POST", preview_path, h.upload("date.csv", csv), cookie=cookie, csrf=csrf)
        expect(status, 422, "csv transformed date")
        if "改用 .xlsx 导入" not in csv_err["error"]["message"]:
            raise AssertionError("CSV xlsx hint missing")

        evidence["checks"] += [["preview_commit", 201, "PASS"], ["commit_guards", 404, "other/cross/demoted/race/replay"], ["D4", 422, "rows=2,4"], ["D5", 201, "warning+hint"], ["D7", 422, "typed provenance"]]
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    finally:
        h.tearDown()


if __name__ == "__main__":
    main()

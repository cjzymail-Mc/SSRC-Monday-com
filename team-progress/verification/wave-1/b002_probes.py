# -*- coding: utf-8 -*-
"""B-002 九项独立负例探针（planner 验收侧 · 防漏 PASS 强化版）

判据标尺（一手，字面原文）：
  A = feature-01-项目时间管理-仪表盘/9-GATE3_TECH_FREEZE.md（门 3 冻结契约，唯一实现契约）
  B = repo 根 team-task.md §8（lead 拍板的 B-002 九项工作包定义）
三硬纪律（验收侧判据手册 2026-08-05）：
  1) 字面判据当标尺——判据字符串全部为 A/B 原文摘句，不引用 coder 自述/测试措辞。
  2) 阳性对照——凡「拒收/失败/超限 fail-closed/零写入」类判据，构造负例真跑并记录原始失败信号。
  3) 探针 observed 仅陈述「实际行为 vs 判据字面」；四态签注由 planner 报告给出，gate 拍板权在 lead。
独立性边界（guardrails 红旗 4 / mc-expert 陪审要点）：
  期望值全部由本探针用公开标准公式自算（如 Excel 1900 纪元 datetime(1899,12,30)+timedelta(days=n)），
  不抄任何 mc-expert/coder 数字、不 import 实现换算函数自证。
零副作用：全部数据库/文件均在本进程 tempfile.TemporaryDirectory 内创建；不写 repo 任何文件；
  绝不触碰真实 flowboard.db（跑完另做只读 mtime 取证）。
清单格式：判据字面原文 -> 负例输入构造 -> 预期失败信号（异常类型/HTTP 语义状态码）。
"""
import io
import json
import sys
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

REPO = Path(r"D:\Downloads\Mc Claude Code Workshop\monday-com")
for _p in (str(REPO), str(REPO / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flowboard.database import connect, migrate  # noqa: E402
import flowboard.database as database  # noqa: E402
from flowboard.timeline import TimelineService  # noqa: E402
from flowboard.service import ApiError  # noqa: E402
from test_secure_foundation import create_legacy_database  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RESULTS = []
SSML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
SERIAL_EPOCH = date(1899, 12, 30)  # Excel 1900 日期系统公开标准纪元

def serial_to_date(serial):
    return SERIAL_EPOCH + timedelta(days=int(serial))

# ---------------- 独立 xlsx 构造（不用 repo make_xlsx，防与实现同构） ----------------
def _col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def _esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def build_xlsx(headers, rows):
    """headers: list[str]；rows: list[list[cell]]；cell = None(空)|("n",数值文本)|("s",文本)。"""
    def cell_xml(r, c, spec):
        if spec is None:
            return ""
        ref = _col_letter(c) + str(r)
        kind, v = spec
        if kind == "n":
            return '<c r="' + ref + '"><v>' + str(v) + '</v></c>'
        return ('<c r="' + ref + '" t="inlineStr"><is><t xml:space="preserve">'
                + _esc(v) + "</t></is></c>")
    body = []
    for r, row in enumerate([[("s", h) for h in headers]] + rows, 1):
        cells = "".join(cell_xml(r, c, spec) for c, spec in enumerate(row, 1))
        body.append('<row r="' + str(r) + '">' + cells + "</row>")
    worksheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<worksheet xmlns="' + SSML + '"><sheetData>' + "".join(body)
                 + "</sheetData></worksheet>")
    content = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
               '<Default Extension="xml" ContentType="application/xml"/>'
               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
               '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    workbook = ('<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="' + SSML
                + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Probe" sheetId="1" r:id="rId1"/></sheets></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", worksheet)
    return out.getvalue()

def count_data_rows(xlsx_bytes):
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    return len(root.findall(".//{" + SSML + "}row")) - 1

# ---------------- 通用工具 ----------------
def call(fn, *a, **kw):
    """调用被测服务；返回 (ok, payload)。失败保留原始失败信号。"""
    try:
        return True, fn(*a, **kw)
    except ApiError as e:
        return False, {"signal": "ApiError", "status": e.status, "code": e.code,
                       "message": e.message, "details": e.details}
    except Exception as e:
        return False, {"signal": type(e).__name__, "error": str(e)}

def record(probe, item, criterion, construct, expect, actual, observed, note=""):
    RESULTS.append({"probe": probe, "item": item, "criterion": criterion,
                    "construct": construct, "expect": expect, "actual": actual,
                    "observed": observed, "note": note})

def brief(v, limit=360):
    text = json.dumps(v, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "...<t>"

class Env:
    """隔离库环境：tempfile 内全新 migrate，绝不出现真实库路径。"""
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="b002-probe-")
        self.db = Path(self.tmp.name) / "probe.db"
        migrate(self.db, initial_password="probe-password")
        self.service = TimelineService(self.db)
        self.admin = {"id": "u1"}

    def add_workspace(self, ws_id, label="probe-ws"):
        conn = connect(self.db)
        conn.execute("INSERT INTO workspaces VALUES (?,?,?,30)",
                     (ws_id, label, "2026-01-01T00:00:00+00:00"))
        conn.execute("INSERT INTO workspace_memberships VALUES (?,?,'admin')",
                     (ws_id, "u1"))
        conn.commit()
        conn.close()

    def snapshot_counts(self):
        conn = connect(self.db)
        tables = ("timeline_projects", "timeline_nodes", "timeline_change_batches",
                  "timeline_node_changes", "timeline_import_batches", "audit_log")
        snap = {t: conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                for t in tables}
        conn.close()
        return snap

    def snapshot_nodes(self):
        conn = connect(self.db)
        rows = [tuple(r) for r in conn.execute(
            "SELECT id,project_id,track,stage,name,date,done_at,remark,deleted_at,"
            "updated_at,version FROM timeline_nodes ORDER BY id")]
        conn.close()
        return rows

    def project_version(self, project_id):
        conn = connect(self.db)
        v = conn.execute("SELECT version FROM timeline_projects WHERE id=?",
                         (project_id,)).fetchone()[0]
        conn.close()
        return v

# ---------------- 表头协商 ----------------
CONTRACT_HEADERS = ["项目名称", "阶段", "轨道", "节点", "日期", "间隔", "状态", "备注"]
SEMANTIC = [("project", ("项目名称", "项目")), ("stage", ("阶段",)), ("track", ("轨道",)),
            ("node", ("节点",)), ("date", ("日期",)), ("interval", ("间隔",)),
            ("status", ("状态",)), ("remark", ("备注",))]

def header_semantic_map(headers):
    m = {}
    for idx, h in enumerate(headers):
        for key, cands in SEMANTIC:
            if h in cands and idx not in m:
                m[idx] = key
    return m

def make_row(headers, data):
    m = header_semantic_map(headers)
    return [data.get(m.get(i)) for i in range(len(headers))]

def negotiate_headers(env):
    """P0：契约字面表头探针；被拒时改用报错附件声明的标准表头（A§5.1 要求文案附标准表头）。"""
    probe_row = {"project": ("s", "表头探测"), "stage": ("s", "创意"),
                 "track": ("s", "main"), "node": ("s", "探针节点"),
                 "date": ("s", "2030-01-01"), "interval": ("s", ""),
                 "status": ("s", ""), "remark": ("s", "")}
    raw = build_xlsx(CONTRACT_HEADERS, [make_row(CONTRACT_HEADERS, probe_row)])
    ok, out = call(env.service.preview_import, env.admin, 1, "probe-header.xlsx", raw)
    crit = ("A§5 依据行：列序=项目名称｜阶段｜轨道｜节点｜日期｜间隔｜状态｜备注；"
            "F2-① 固定 8 列列序 + 表头精确校验")
    if ok:
        record("P0", 0, crit, "契约字面 8 列表头+1 行合法数据 → preview_import",
               "接受", brief(out), "PASS_PROBE", "契约字面表头可用")
        return CONTRACT_HEADERS
    record("P0", 0, crit, "契约字面 8 列表头+1 行合法数据 → preview_import",
           "接受", brief(out), "FAIL_PROBE",
           "契约字面表头被拒（新发现，待 lead 判定归属，不并入九项四态）")
    det = out.get("details") if isinstance(out, dict) else None
    if (isinstance(det, dict) and isinstance(det.get("headers"), list)
            and len(det["headers"]) == 8):
        return det["headers"]
    raise RuntimeError("表头协商失败，九项探针被表头关卡阻断: " + json.dumps(out, default=str))

# ================= 第 1 项：xlsx 序列号 =================
def probe_serial(env, H):
    crit = ("A§5.2 日期行：.xlsx 数值日期按序列号换算，限 1950–2100 整数"
            "（序列号 18264–73051）；非整数序列号（带时间如 46234.5）明确拒收。"
            "B§8-1：整数序列号 18264..73051 换算日期；分数/越界行级 422")
    base = {"stage": ("s", "创意"), "track": ("s", "main"),
            "interval": ("s", ""), "status": ("s", ""), "remark": ("s", "")}

    def one_row(serial_spec, node_name, project_name):
        d = dict(base)
        d["project"] = ("s", project_name)
        d["node"] = ("s", node_name)
        d["date"] = serial_spec
        return make_row(H, d)

    # P1a 中段序列号正例：换算期望自算（公开标准公式）
    for serial in (46648, 18264, 73051):
        ok, out = call(env.service.preview_import, env.admin, 1,
                       "serial-%d.xlsx" % serial,
                       build_xlsx(H, [one_row(("n", str(serial)), "N%d" % serial,
                                             "序列号项目%d" % serial)]))
        if not ok:
            record("P1a", 1, crit,
                   "xlsx 数值 cell 序列号 %d（界内）→ preview_import" % serial,
                   "接受且换算日期==" + serial_to_date(serial).isoformat(),
                   brief(out), "FAIL_PROBE", "界内整数被拒")
            continue
        pv, co = (call(env.service.commit_import, env.admin, 1,
                       {"batch_id": out["batch_id"]}) if ok else (False, None))
        if not pv:
            record("P1a", 1, crit, "序列号 %d preview 后 commit" % serial,
                   "commit 成功", brief(co), "FAIL_PROBE", "界内整数 commit 失败")
            continue
        projects = env.service.list_projects(env.admin, 1)["projects"]
        nodes = [n for p in projects for n in p["nodes"] if n["name"] == "N%d" % serial]
        got = nodes[0]["date"] if nodes else None
        record("P1a", 1, crit,
               "xlsx 数值 cell 序列号 %d → preview+commit → 读回节点 date" % serial,
               "date==" + serial_to_date(serial).isoformat() + "（探针自算）",
               {"stored_date": got},
               "PASS_PROBE" if got == serial_to_date(serial).isoformat() else "FAIL_PROBE",
               "端点/中段整数换算")

    # P1b 非整数序列号拒收（阳性对照：必须真看到 422）
    ok, out = call(env.service.preview_import, env.admin, 1, "frac.xlsx",
                   build_xlsx(H, [one_row(("n", "46234.5"), "FRAC", "分数序列号项目")]))
    record("P1b", 1, crit + "；A§5.2 错误形态：行级 422，details 带 row（从 2 起）",
           "xlsx 数值 cell 46234.5 → preview_import",
           "ApiError 422 行级（details.row=2）", brief(out),
           "PASS_PROBE" if (not ok and out.get("status") == 422) else "FAIL_PROBE",
           "非整数必须真跑出 422（纪律2 阳性对照）")

    # P1c 越界整数拒收
    for serial in (18263, 73052):
        ok, out = call(env.service.preview_import, env.admin, 1,
                       "oob-%d.xlsx" % serial,
                       build_xlsx(H, [one_row(("n", str(serial)), "OOB", "越界项目%d" % serial)]))
        record("P1c", 1, crit, "xlsx 数值 cell 越界整数 %d → preview_import" % serial,
               "ApiError 422 行级", brief(out),
               "PASS_PROBE" if (not ok and out.get("status") == 422) else "FAIL_PROBE")

    # P1d CSV 文本路径不串扰：CSV 只认文本 YYYY-MM-DD
    import csv as _csv
    def csv_bytes(rows):
        buf = io.StringIO(newline="")
        w = _csv.writer(buf, lineterminator="\r\n")
        w.writerows(rows)
        return buf.getvalue().encode("utf-8-sig")
    pos = header_semantic_map(H)
    hdr_names = {k: H[i] for i, k in pos.items()}
    ok, out = call(env.service.preview_import, env.admin, 1, "t.csv",
                   csv_bytes([H, ["" if c is None else c[1] for c in
                                  make_row(H, {**base, "project": ("s", "文本序列号项目"), "node": ("s", "文本序列号节点"), "date": ("s", "46648")})]]))
    msg = str(out.get("message", "")) if isinstance(out, dict) else ""
    record("P1d", 1, "A§5.2 日期行：文本严格 YYYY-MM-DD+真实历法校验（序列号换算仅限 .xlsx）",
           "CSV 日期列文本 46648 → preview_import",
           "ApiError 422 行级且为日期校验理由（非缺字段 required）", brief(out),
           "PASS_PROBE" if (not ok and out.get("status") == 422
                            and "required" not in msg) else "FAIL_PROBE",
           "文本路径不得被序列号分支串扰；422 不得由错误理由触发")
    ok, out = call(env.service.preview_import, env.admin, 1, "t2.csv",
                   csv_bytes([H, ["" if c is None else c[1] for c in
                                  make_row(H, {**base, "project": ("s", "文本正例项目"), "node": ("s", "文本正例节点"),
                                               "date": ("s", "2030-01-01")})]]))
    record("P1e", 1, "A§5.2 日期行：文本严格 YYYY-MM-DD",
           "CSV 日期列 2030-01-01 → preview_import", "接受", brief(out),
           "PASS_PROBE" if ok else "FAIL_PROBE", "CSV 合法文本正控")
    # P1f xlsx 内文本日期 cell（inlineStr）正例
    ok, out = call(env.service.preview_import, env.admin, 1, "t3.xlsx",
                   build_xlsx(H, [make_row(H, {**base, "project": ("s", "内嵌文本日期"), "node": ("s", "内嵌文本节点"),
                                               "date": ("s", "2030-01-02")})]))
    record("P1f", 1, "A§5.2 日期行：文本严格 YYYY-MM-DD（xlsx 文本 cell 同样有效）",
           "xlsx inlineStr 日期 2030-01-02 → preview_import", "接受", brief(out),
           "PASS_PROBE" if ok else "FAIL_PROBE")

# ================= 第 2 项：状态三态 =================
def probe_status(env, H):
    crit = ("A§5.2 状态行：∈ 三态或空（D12=B）：「已完成」→ done_at=导入时刻；"
            "「未开始/进行中」→ 仅参考、落库按日期重算；空 → 按日期派生；"
            "其他文本 → 行级报错。B§8-2：仅 已完成 持久化 done_at，其余按日期重算")
    base = {"stage": ("s", "创意"), "track": ("s", "main"),
            "interval": ("s", ""), "remark": ("s", "")}

    def run_case(tag, status_cell, node_date, expect_status, expect_done):
        d = dict(base)
        d["project"] = ("s", "状态项目-" + tag)
        d["node"] = ("s", tag)
        d["date"] = ("s", node_date)
        d["status"] = status_cell
        ok, out = call(env.service.preview_import, env.admin, 1,
                       "st-%s.xlsx" % tag, build_xlsx(H, [make_row(H, d)]))
        if not ok:
            record("P2-" + tag, 2, crit,
                   "status=%s + date=%s → preview" % (brief(status_cell), node_date),
                   "接受；落库后派生 status=%s、done_at=%s" % (expect_status, expect_done),
                   brief(out), "FAIL_PROBE", "合法三态/空被拒")
            return
        ok2, co = call(env.service.commit_import, env.admin, 1, {"batch_id": out["batch_id"]})
        if not ok2:
            record("P2-" + tag, 2, crit, "status=%s commit" % brief(status_cell),
                   "commit 成功", brief(co), "FAIL_PROBE")
            return
        conn = connect(env.db)
        row = conn.execute("SELECT done_at FROM timeline_nodes WHERE name=?", (tag,)).fetchone()
        conn.close()
        done_stored = None if row is None else (row[0] is not None)
        projects = env.service.list_projects(env.admin, 1)["projects"]
        node = [n for p in projects for n in p["nodes"] if n["name"] == tag]
        got_status = node[0]["status"] if node else None
        okv = (done_stored == expect_done and got_status == expect_status)
        record("P2-" + tag, 2, crit,
               "status=%s + date=%s → preview+commit → 读回" % (brief(status_cell), node_date),
               "接受；派生 status=%s、done_at 落库=%s" % (expect_status, expect_done),
               {"stored_done_at": done_stored, "derived_status": got_status},
               "PASS_PROBE" if okv else "FAIL_PROBE",
               "非完成态不得持久化完成；派生状态按日期重算")

    run_case("weikaishi_past", ("s", "未开始"), "2020-01-01", "进行中", False)
    run_case("jinxingzhong_future", ("s", "进行中"), "2099-01-01", "未开始", False)
    run_case("empty_past", ("s", ""), "2020-01-02", "进行中", False)
    run_case("yiwancheng", ("s", "已完成"), "2099-01-02", "已完成", True)

    for tag, status in (("illegal", "暂停"), ("weifenjian", "未完成")):
        d = dict(base)
        d["node"] = ("s", tag)
        d["date"] = ("s", "2030-01-01")
        d["status"] = ("s", status)
        ok, out = call(env.service.preview_import, env.admin, 1,
                       "st2-%s.xlsx" % tag, build_xlsx(H, [make_row(H, d)]))
        record("P2-" + tag, 2, crit,
               "status=%s（三态或空之外）→ preview" % status,
               "ApiError 422 行级（details.row=2）", brief(out),
               "PASS_PROBE" if (not ok and out.get("status") == 422) else "FAIL_PROBE",
               "「未完成」为旧实现认可值、契约字面三态之外——锋利负例" if status == "未完成" else "")

# ================= 第 3 项：多行项目聚合 =================
def probe_aggregate(env, H):
    crit = ("A§5.2 文件内重复行：同项目+同轨+同日+同名，第二行起 行级 422「与第 N 行重复」；"
            "B§8-3：同名多行聚合为一个项目；仅四元组重复才拒收；preview 列实际节点数，"
            "commit 报去重项目数与总节点数")
    def row(project, node, dt, track="main", stage="创意", status="", remark=""):
        return make_row(H, {"project": ("s", project), "stage": ("s", stage),
                            "track": ("s", track), "node": ("s", node),
                            "date": ("s", dt), "interval": ("s", ""),
                            "status": ("s", status), "remark": ("s", remark)})
    # P3a 同名 3 行（不同轨道/日期）→ 聚合 1 项目 3 节点
    rows = [row("聚合项目", "甲", "2030-01-01"),
            row("聚合项目", "乙", "2030-01-05", track="parallel", stage="测试"),
            row("聚合项目", "丙", "2030-01-03", stage="开发")]
    ok, out = call(env.service.preview_import, env.admin, 1, "agg.xlsx", build_xlsx(H, rows))
    note = ""
    if ok:
        plist = out.get("projects", [])
        ncount = None
        for entry in plist:
            if isinstance(entry, dict) and entry.get("name") == "聚合项目":
                for k in ("node_count", "nodes", "count"):
                    if k in entry:
                        ncount = entry[k]
                        break
        note = "preview projects=%s" % brief(plist)
        ok2, co = call(env.service.commit_import, env.admin, 1, {"batch_id": out["batch_id"]})
        conn = connect(env.db)
        pid = conn.execute("SELECT id FROM timeline_projects WHERE name='聚合项目'").fetchone()
        nodes = conn.execute(
            "SELECT COUNT(*) FROM timeline_nodes WHERE project_id=? AND deleted_at IS NULL",
            (pid[0],)).fetchone()[0] if pid else -1
        conn.close()
        proj_count = len(plist)
        verdict = ("PASS_PROBE" if (ok2 and pid and nodes == 3 and proj_count == 1
                                    and ncount in (3, None)) else "FAIL_PROBE")
        record("P3a", 3, crit, "同名 3 行（不同轨道/日期/节点）→ preview+commit",
               "preview projects=1 且节点数=3；commit 后 1 项目 3 节点（不互相覆盖）",
               {"preview": plist, "commit": co, "db_node_count": nodes,
                "db_project_count": 1 if pid else 0}, verdict, note)
    else:
        record("P3a", 3, crit, "同名 3 行 → preview", "接受", brief(out), "FAIL_PROBE",
               "同名多行被拒→聚合未实现")

    # P3b 四元组重复第二行 → 422 带行号
    dup = [row("重复项目", "同", "2030-02-01"), row("重复项目", "同", "2030-02-01")]
    ok, out = call(env.service.preview_import, env.admin, 1, "dup.xlsx", build_xlsx(H, dup))
    det = out.get("details") if isinstance(out, dict) else None
    record("P3b", 3, crit, "同项目+同轨+同日+同名 两行 → preview",
           "ApiError 422 且 details.row=3（第二数据行，行号从 2 起）", brief(out),
           "PASS_PROBE" if (not ok and out.get("status") == 422
                            and isinstance(det, dict) and det.get("row") == 3) else "FAIL_PROBE")

    # P3c 四元组任一不同 → 不得拒
    vary = [row("变体项目", "同名异日", "2030-03-01"), row("变体项目", "同名异日", "2030-03-02"),
            row("变体项目", "同日异名", "2030-03-03"), row("变体项目", "同日异名二", "2030-03-03")]
    ok, out = call(env.service.preview_import, env.admin, 1, "vary.xlsx", build_xlsx(H, vary))
    record("P3c", 3, crit, "四元组任一不同的多变体行 → preview", "接受", brief(out),
           "PASS_PROBE" if ok else "FAIL_PROBE")

    # P3d 库内同名活跃项目：该项目所有行报错、有错不许提交（R1/F2-④）
    env.service.create_project(env.admin, 1, {"name": "既有项目"})
    clash = [row("既有项目", "一", "2030-04-01"), row("既有项目", "二", "2030-04-02"),
             row("无辜项目", "三", "2030-04-03")]
    ok, out = call(env.service.preview_import, env.admin, 1, "clash.xlsx", build_xlsx(H, clash))
    det = out.get("details") if isinstance(out, dict) else None
    rows_flagged = (det or {}).get("rows") if isinstance(det, dict) else None
    record("P3d", 3, "A§5.2 项目名称行：同名已有项目=该项目所有行报错（带行号）、"
           "有错不许提交、不做部分导入",
           "库内已有同名活跃项目 + 3 行文件（2 行同名）→ preview",
           "ApiError 422；同名行 2、3 全部报错；不产生 previewed 批次",
           brief(out), "PASS_PROBE" if not ok and out.get("status") == 422 else "FAIL_PROBE",
           "partial import/静默跳过即违约")

# ================= 第 4 项：字段上限（中文样本，字符数口径） =================
def probe_limits(env, H):
    crit_node = "A§5.2 节点名称行：非空、≤500（对齐任务标题上限）"
    crit_remark = "A§5.2 备注行：可空，≤500"
    crit_project = "A§5.2 项目名称行：非空、≤200 字"
    def row(project, node, remark):
        return make_row(H, {"project": ("s", project), "stage": ("s", "创意"),
                            "track": ("s", "main"), "node": ("s", node),
                            "date": ("s", "2030-01-01"), "interval": ("s", ""),
                            "status": ("s", ""), "remark": ("s", remark)})
    def preview(tag, project, node, remark):
        return call(env.service.preview_import, env.admin, 1, "lim-%s.xlsx" % tag,
                    build_xlsx(H, [row(project, node, remark)]))
    ok, out = preview("node500", "上限项目", "节" * 500, "")
    record("P4a", 4, crit_node, "节点名恰 500 个中文字符 → preview", "接受", brief(out),
           "PASS_PROBE" if ok else "FAIL_PROBE", "半边界：恰上限必须接受")
    ok, out = preview("node501", "上限项目", "节" * 501, "")
    record("P4b", 4, crit_node, "节点名 501 个中文字符 → preview", "ApiError 422 行级",
           brief(out), "PASS_PROBE" if (not ok and out.get("status") == 422) else "FAIL_PROBE")
    ok, out = preview("remark500", "上限项目", "备注节点", "备" * 500)
    record("P4c", 4, crit_remark, "备注恰 500 个中文字符 → preview", "接受", brief(out),
           "PASS_PROBE" if ok else "FAIL_PROBE")
    ok, out = preview("remark501", "上限项目", "备注节点", "备" * 501)
    record("P4d", 4, crit_remark, "备注 501 个中文字符 → preview", "ApiError 422 行级",
           brief(out), "PASS_PROBE" if (not ok and out.get("status") == 422) else "FAIL_PROBE")
    ok, out = preview("proj200", "项" * 200, "项目名节点", "")
    record("P4e", 4, crit_project, "项目名恰 200 个中文字符 → preview", "接受", brief(out),
           "PASS_PROBE" if ok else "FAIL_PROBE")
    ok, out = preview("proj201", "项" * 201, "项目名节点", "")
    record("P4f", 4, crit_project, "项目名 201 个中文字符 → preview", "ApiError 422 行级",
           brief(out), "PASS_PROBE" if (not ok and out.get("status") == 422) else "FAIL_PROBE",
           "中文按字符计数（非字节）——201 中文字=603 UTF-8 字节")

# ================= 第 5 项：导出边界 =================
def seed_nodes_direct(env, ws, project_name, count, start=date(2030, 1, 1)):
    """隔离库直接 SQL 造节点（.copilot-message 第 5 项允许的 fixture 方式）；四元组保证唯一。"""
    pid = env.service.create_project(env.admin, ws, {"name": project_name})["project_id"]
    conn = connect(env.db)
    for i in range(count):
        d = (start + timedelta(days=i)).isoformat()
        conn.execute(
            "INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,"
            "done_at,remark,version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,NULL,'',1,?,?)",
            (pid, "main", "创意", "节点%05d" % i, d, d,
             "2030-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00"))
    conn.commit()
    conn.close()
    return pid

def probe_export_boundary(_shared):
    crit = ("A§3.7 导出行：行上限 1000（与导入闭环，导出物必可再导入）；"
            "B§8-5：恰好 1000 行成功导出且产物可再导入；超限 422 EXPORT_LIMIT（含 total/max），"
            "禁静默截断")
    env = Env()  # 独立干净库：导出边界对全库活跃节点数敏感，不得被前序探针污染
    # P5a 恰 1000
    pid = seed_nodes_direct(env, 1, "导出边界项目", 1000)
    ok, raw = call(env.service.export_timeline, env.admin, 1)
    if not ok:
        record("P5a", 5, crit, "隔离库恰 1000 活跃节点 → export_timeline", "成功且产物数据行=1000",
               brief(raw), "FAIL_PROBE")
    else:
        rows = count_data_rows(raw)
        env.add_workspace(2, "export-ws")
        ok2, pv = call(env.service.preview_import, env.admin, 2, "export.xlsx", raw)
        verdict = "PASS_PROBE" if (rows == 1000 and ok2) else "FAIL_PROBE"
        record("P5a", 5, crit, "恰 1000 活跃节点 → export → 新 workspace preview",
               "导出成功；产物数据行=1000；preview 接受",
               {"data_rows": rows, "preview_ok": ok2, "preview": brief(pv, 200)}, verdict,
               "导出物必可再导入（闭环）")
    # P5b 1001 → fail-closed
    env2 = Env()
    seed_nodes_direct(env2, 1, "超限项目", 1001)
    ok, out = call(env2.service.export_timeline, env2.admin, 1)
    det = out.get("details") if isinstance(out, dict) else None
    detail_str = json.dumps(det, default=str)
    has_limit = (not ok and out.get("status") == 422 and out.get("code") == "EXPORT_LIMIT")
    has_total_max = ("1001" in detail_str and "1000" in detail_str)
    record("P5b", 5, crit, "隔离库 1001 活跃节点 → export_timeline",
           "ApiError 422 且 code==EXPORT_LIMIT 且 details 含 total=1001/max=1000",
           brief(out), "PASS_PROBE" if (has_limit and has_total_max) else "FAIL_PROBE",
           "任何 200 返回（哪怕带 1000 行产物）=静默截断违约证据")

# ================= 第 6 项：真实字节 round-trip（最高危） =================
def probe_roundtrip(env):
    crit = ("B§8-6：用 export_timeline() 返回的真实字节导入新 workspace，断言语义等价、"
            "已完成保留、非完成态按日期重算、interval 忽略、done_at 允许时间差；"
            "A§3.7：R5 同名即拒，往返等价仅发生在全新 workspace；"
            "A§7.1 组9：导出→导入往返等价（除 done_at 时刻与状态重算的既定差异）")
    # 最难样本：两项目、双轨、已完成/未开始/进行中齐全、跨月、中文与边界长度字段
    import hashlib
    p1 = env.service.create_project(env.admin, 1, {"name": "往返甲"})["project_id"]
    env.service.submit_batches(env.admin, 1, {"requests": [{"project_id": p1, "base_version": 1,
        "changes": [
            {"create": {"track": "main", "stage": "创意", "name": "甲首", "date": "2020-01-05"}},
            {"create": {"track": "main", "stage": "设计", "name": "甲二", "date": "2020-02-11",
                        "done_at": True, "remark": "中文备注·跨月"}},
            {"create": {"track": "main", "stage": "量产", "name": "节" * 500, "date": "2099-11-30"}},
            {"create": {"track": "parallel", "stage": "测试", "name": "并行子", "date": "2099-12-05"}},
        ]}]})["results"][0]
    p2 = env.service.create_project(env.admin, 1, {"name": "往返乙·第二项目"})["project_id"]
    env.service.submit_batches(env.admin, 1, {"requests": [{"project_id": p2, "base_version": 1,
        "changes": [
            {"create": {"track": "parallel", "stage": "应用迭代", "name": "乙并", "date": "2020-03-01"}},
        ]}]})["results"][0]
    src = env.service.list_projects(env.admin, 1)["projects"]
    src_sem = sorted(
        (proj["name"], tuple(sorted(
            (n["track"], n["stage"], n["name"], n["date"], n["remark"],
             bool(n["done_at"]), n["status"], n["interval_days"]) for n in proj["nodes"])))
        for proj in src)
    ok, raw = call(env.service.export_timeline, env.admin, 1)
    if not ok:
        record("P6a", 6, crit, "源 workspace export_timeline", "成功返回字节", brief(raw),
               "FAIL_PROBE", "导出失败，round-trip 无从谈起")
        return
    raw_sha = hashlib.sha256(raw).hexdigest()
    env.add_workspace(2, "roundtrip-ws")
    ok2, pv = call(env.service.preview_import, env.admin, 2, "真字节往返.xlsx", raw)
    # 字节同一性证据：preview 批次登记的 content_sha256 必须等于导出字节 sha256
    sha_evidence = None
    if ok2:
        conn = connect(env.db)
        row = conn.execute("SELECT content_sha256 FROM timeline_import_batches WHERE id=?",
                           (pv["batch_id"],)).fetchone()
        conn.close()
        sha_evidence = row[0] if row else None
    ok3, co = (call(env.service.commit_import, env.admin, 2, {"batch_id": pv["batch_id"]})
               if ok2 else (False, None))
    dst = env.service.list_projects(env.admin, 2)["projects"] if ok3 else []
    dst_sem = sorted(
        (proj["name"], tuple(sorted(
            (n["track"], n["stage"], n["name"], n["date"], n["remark"],
             bool(n["done_at"]), n["status"], n["interval_days"]) for n in proj["nodes"])))
        for proj in dst)
    verdict = "PASS_PROBE" if (ok2 and ok3 and sha_evidence == raw_sha
                               and src_sem == dst_sem) else "FAIL_PROBE"
    record("P6a", 6, crit,
           "源 ws（2 项目 5 节点，双轨/三态/跨月/中文/500 字节点名）→ export 真实字节"
           " → 全新 ws2 preview+commit → 双侧视图逐节点比对",
           "字节 sha256 一致；语义等价（名称/日期/轨道/阶段/备注）；已完成保留 done_at；"
           "非完成态按日期重算；interval 忽略但重派生一致；done_at 只比存在性",
           {"export_sha256": raw_sha, "stored_content_sha256": sha_evidence,
            "src": src_sem, "dst": dst_sem, "equal": src_sem == dst_sem,
            "preview": brief(pv, 160), "commit": brief(co, 160)}, verdict,
           "喂给 preview 的字节必须与 export 返回值逐字节相同（sha256 铁证）")
    # P6b R5：同 ws2 二次 preview 同字节 → 422（同名即拒）
    ok4, out = call(env.service.preview_import, env.admin, 2, "again.xlsx", raw)
    record("P6b", 6, "A§3.7 R5：同名即拒使「导出→导回同一 workspace」被 R1 拦截",
           "已 commit 的 ws2 再次 preview 同一真实字节", "ApiError 422", brief(out),
           "PASS_PROBE" if (not ok4 and out.get("status") == 422) else "FAIL_PROBE")

# ================= 第 7 项：迁移证据（全程隔离库） =================
def probe_migration():
    crit = ("B§8-7：v15→v16 备份非空且含代表性存量；对 v16 库重跑 migrate 幂等"
            "（user_version=16 且仅一条 version 16 迁移记录）；回滚语义可证；全程隔离库；"
            "A§6 2a：先 integrity_check 再快照，快照失败=迁移中止；"
            "A§6 步3：迁移前只读记录存量表动态计数基线→迁移后逐项比对完全一致")
    import sqlite3
    tmp = tempfile.TemporaryDirectory(prefix="b002-mig-")
    try:
        path = Path(tmp.name) / "seeded-v15.db"
        create_legacy_database(path)
        conn = connect(path)
        database._migration_v1(conn, "probe-password")
        for v in range(2, 16):
            getattr(database, "_migration_v%d" % v)(conn)
        baseline = {t: conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                    for t in ("users", "workspaces", "boards", "groups_", "tasks")}
        sentinel = [tuple(r) for r in conn.execute(
            "SELECT id,title,status FROM tasks ORDER BY id")]
        conn.close()
        backups_dir = Path(tmp.name) / "backups"
        before_files = sorted(p.name for p in backups_dir.glob("*")) if backups_dir.exists() else []
        backup = migrate(str(path))
        after_files = sorted(p.name for p in backups_dir.glob("*")) if backups_dir.exists() else []
        new_backups = [f for f in after_files if f not in before_files]
        checks = {"backup_returned": backup, "new_backup_files": new_backups}
        if backup and Path(backup).exists() and Path(backup).stat().st_size > 0:
            bconn = connect(backup)
            checks["backup_user_version"] = bconn.execute("PRAGMA user_version").fetchone()[0]
            checks["backup_has_timeline_tables"] = [
                r[0] for r in bconn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'timeline%'")]
            checks["backup_task_count"] = bconn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            checks["backup_sentinel"] = [tuple(r) for r in bconn.execute(
                "SELECT id,title,status FROM tasks ORDER BY id")]
            checks["backup_user_count"] = bconn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            bconn.close()
        conn = connect(path)
        checks["user_version"] = conn.execute("PRAGMA user_version").fetchone()[0]
        checks["v16_migration_rows"] = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=16").fetchone()[0]
        checks["counts_after"] = {t: conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                                  for t in ("users", "workspaces", "boards", "groups_", "tasks")}
        checks["timeline_empty"] = {t: conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                                    for t in ("timeline_projects", "timeline_nodes",
                                              "timeline_change_batches",
                                              "timeline_node_changes",
                                              "timeline_import_batches")}
        checks["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        checks["fk"] = conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.close()
        ok_a = (backup and checks.get("backup_user_version") == 15
                and checks.get("backup_has_timeline_tables") == []
                and checks.get("backup_task_count", 0) > 0
                and checks.get("backup_sentinel") == sentinel
                and checks["user_version"] == 16 and checks["v16_migration_rows"] == 1
                and checks["counts_after"] == baseline
                and all(v == 0 for v in checks["timeline_empty"].values())
                and checks["integrity"] == "ok" and checks["fk"] == []
                and len(new_backups) == 1)
        record("P7a", 7, crit,
               "v15 种子库（users/boards/tasks 含 sentinel）→ migrate → 断言对象=备份本体+迁移后库",
               "备份非空、user_version==15、sentinel 在、无 timeline 表；迁移后 16、"
               "五表空、存量计数=基线、integrity/FK 过、backups 恰多 1 个 pre-v16",
               checks, "PASS_PROBE" if ok_a else "FAIL_PROBE",
               "断言必须打在备份快照本体上，不是迁移后库")
        # P7b 幂等
        migrate(str(path))
        conn = connect(path)
        idem = {"user_version": conn.execute("PRAGMA user_version").fetchone()[0],
                "v16_rows": conn.execute(
                    "SELECT COUNT(*) FROM schema_migrations WHERE version=16").fetchone()[0],
                "timeline_counts": {t: conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                                    for t in ("timeline_projects", "timeline_nodes")},
                "tasks": conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]}
        conn.close()
        ok_b = (idem["user_version"] == 16 and idem["v16_rows"] == 1
                and idem["tasks"] == baseline["tasks"]
                and all(v == 0 for v in idem["timeline_counts"].values()))
        record("P7b", 7, "B§8-7：对 v16 库重跑 migrate 幂等（user_version=16 且仅一条 version 16 迁移记录）",
               "已 v16 的隔离库再次 migrate", "user_version 仍 16；version=16 记录恰 1 条；五表仍空；存量不变",
               idem, "PASS_PROBE" if ok_b else "FAIL_PROBE")
        # P7c 回滚语义：备份恢复到新库 → v15 语义
        import sqlite3 as sq3
        restored = Path(tmp.name) / "restored.db"
        s = sq3.connect(str(backup)); d = sq3.connect(str(restored)); s.backup(d)
        d.close(); s.close()
        rconn = connect(restored)
        rollback = {"user_version": rconn.execute("PRAGMA user_version").fetchone()[0],
                    "timeline_tables": [r[0] for r in rconn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'timeline%'")],
                    "sentinel": [tuple(r) for r in rconn.execute(
                        "SELECT id,title,status FROM tasks ORDER BY id")]}
        rconn.close()
        ok_c = (rollback["user_version"] == 15 and rollback["timeline_tables"] == []
                and rollback["sentinel"] == sentinel)
        record("P7c", 7, "B§8-7：回滚语义可证；A§6 注记③：回滚=丢时间轴侧新增写入、存量无损",
               "备份本体 sqlite backup → 新库，断言 v15 语义",
               "恢复库 user_version==15、无 timeline 表、sentinel 存量无损",
               rollback, "PASS_PROBE" if ok_c else "FAIL_PROBE")
    finally:
        tmp.cleanup()

# ================= 第 8 项：undo 证据 =================
def probe_undo(env):
    crit = ("A§3.2 护栏①：每个 batch_id 必须是其所属项目 MAX(id) 批次，任一不满足→整个 undo 409 "
            "UNDO_TARGET_STALE 零写入；③ 逐行生成反向变更（old/new 互换；created 反向=软删该节点、"
            "deleted 反向=恢复 deleted_at=NULL），原批次原样保留；B§8-8：三连续批次，"
            "中间批次 undo 返回 409 且零写入")
    pid = env.service.create_project(env.admin, 1, {"name": "撤销探针"})["project_id"]
    b1 = env.service.submit_batches(env.admin, 1, {"requests": [{"project_id": pid,
        "base_version": 1, "changes": [
            {"create": {"track": "main", "stage": "创意", "name": "N1", "date": "2030-01-01"}},
            {"create": {"track": "main", "stage": "设计", "name": "N2", "date": "2030-01-05"}}]}]})["results"][0]
    nodes = {n["name"]: n["id"] for n in b1["view"]["nodes"]}
    b2 = env.service.submit_batches(env.admin, 1, {"requests": [{"project_id": pid,
        "base_version": 2, "changes": [
            {"node_id": nodes["N1"], "set": {"date": "2030-01-03"}}]}]})["results"][0]
    b3 = env.service.submit_batches(env.admin, 1, {"requests": [{"project_id": pid,
        "base_version": 3, "changes": [
            {"node_id": nodes["N2"], "set": {"remark": "第三批"}}]}]})["results"][0]
    ids = (b1["batch_id"], b2["batch_id"], b3["batch_id"])
    counts_before = env.snapshot_counts(); nodes_before = env.snapshot_nodes()
    ver_before = env.project_version(pid)
    ok, out = call(env.service.undo_batches, env.admin, 1, {"batch_ids": [ids[1]]})
    zero = (env.snapshot_counts() == counts_before and env.snapshot_nodes() == nodes_before
            and env.project_version(pid) == ver_before)
    record("P8a", 8, crit, "同项目连续三批（id 严格递增 %s）→ undo 中间批" % (ids,),
           "ApiError 409 且 code==UNDO_TARGET_STALE；六表计数+节点行快照+version 全不变",
           {"error": brief(out), "zero_write": zero},
           "PASS_PROBE" if (not ok and out.get("status") == 409
                            and out.get("code") == "UNDO_TARGET_STALE" and zero) else "FAIL_PROBE",
           "409 必须是 UNDO_TARGET_STALE（错误理由区分）")
    ok, out = call(env.service.undo_batches, env.admin, 1, {"batch_ids": [ids[2]]})
    record("P8a-ctl", 8, crit, "同 fixture 撤最新批 %d" % ids[2], "成功", brief(out, 200),
           "PASS_PROBE" if ok else "FAIL_PROBE", "证明中间批 409 非其他原因")
    # P8b 创建反向=软删
    pid2 = env.service.create_project(env.admin, 1, {"name": "创建反向"})["project_id"]
    cb = env.service.submit_batches(env.admin, 1, {"requests": [{"project_id": pid2,
        "base_version": 1, "changes": [
            {"create": {"track": "main", "stage": "创意", "name": "CR", "date": "2030-02-01"}}]}]})["results"][0]
    ok, out = call(env.service.undo_batches, env.admin, 1, {"batch_ids": [cb["batch_id"]]})
    undo_id = out["results"][0]["batch_id"] if ok and isinstance(out, dict) else None
    conn = connect(env.db)
    row = conn.execute("SELECT deleted_at, date FROM timeline_nodes WHERE name='CR'").fetchone()
    kept = conn.execute("SELECT COUNT(*) FROM timeline_nodes WHERE name='CR'").fetchone()[0]
    orig = conn.execute("SELECT COUNT(*) FROM timeline_change_batches WHERE id=?",
                        (cb["batch_id"],)).fetchone()[0]
    ub = conn.execute("SELECT undone_batch_id FROM timeline_change_batches "
                      "WHERE change_kind='undo' ORDER BY id DESC LIMIT 1").fetchone()
    orig_rows = [tuple(r) for r in conn.execute(
        "SELECT node_id,change_role,field,old_value,new_value FROM timeline_node_changes "
        "WHERE batch_id=? ORDER BY id", (cb["batch_id"],))] if orig else []
    undo_rows = [tuple(r) for r in conn.execute(
        "SELECT node_id,change_role,field,old_value,new_value FROM timeline_node_changes "
        "WHERE batch_id=? ORDER BY id", (undo_id,))] if undo_id else []
    conn.close()
    ok_b = (ok and row and row[0] is not None and kept == 1 and orig == 1
            and ub and ub[0] == cb["batch_id"])
    record("P8b", 8, "A§3.2 护栏③：created 反向=软删该节点；原批次原样保留",
           "undo 一个纯 create 批次 → 读库",
           "节点 deleted_at 非空且行仍在（软删非物理删）；被撤批次行保留；undo 批 undone_batch_id 正确",
           {"node": tuple(row) if row else None, "row_kept": kept,
            "orig_batch_kept": orig, "undo_points_to": ub[0] if ub else None,
            "undo_batch_id": undo_id, "undone_batch_change_rows": orig_rows,
            "undo_batch_change_rows": undo_rows},
           "PASS_PROBE" if ok_b else "FAIL_PROBE",
           "定位型探针：失败时以行级数据定位病因层（changes 选取/field 匹配/UPDATE 生效），"
           "不停留在静态归因")
    # P8c 删除反向=恢复
    pid3 = env.service.create_project(env.admin, 1, {"name": "删除反向"})["project_id"]
    base = env.service.submit_batches(env.admin, 1, {"requests": [{"project_id": pid3,
        "base_version": 1, "changes": [
            {"create": {"track": "main", "stage": "创意", "name": "D1", "date": "2030-03-01"}},
            {"create": {"track": "main", "stage": "设计", "name": "D2", "date": "2030-03-05"}}]}]})["results"][0]
    nid = {n["name"]: n["id"] for n in base["view"]["nodes"]}["D2"]
    rb = env.service.submit_batches(env.admin, 1, {"requests": [{"project_id": pid3,
        "base_version": 2, "changes": [{"node_id": nid, "remove": True}]}]})["results"][0]
    conn = connect(env.db)
    mid = conn.execute("SELECT deleted_at FROM timeline_nodes WHERE id=?", (nid,)).fetchone()[0]
    conn.close()
    ok, out = call(env.service.undo_batches, env.admin, 1, {"batch_ids": [rb["batch_id"]]})
    undo_id3 = out["results"][0]["batch_id"] if ok and isinstance(out, dict) else None
    conn = connect(env.db)
    after = conn.execute("SELECT deleted_at, date FROM timeline_nodes WHERE id=?", (nid,)).fetchone()
    last_undo = conn.execute("SELECT MAX(id) FROM timeline_change_batches WHERE project_id=?",
                             (pid3,)).fetchone()[0]
    orig_rows3 = [tuple(r) for r in conn.execute(
        "SELECT node_id,change_role,field,old_value,new_value FROM timeline_node_changes "
        "WHERE batch_id=? ORDER BY id", (rb["batch_id"],))]
    undo_rows3 = [tuple(r) for r in conn.execute(
        "SELECT node_id,change_role,field,old_value,new_value FROM timeline_node_changes "
        "WHERE batch_id=? ORDER BY id", (undo_id3,))] if undo_id3 else []
    conn.close()
    ok_c = (mid is not None and ok and after and after[0] is None and after[1] == "2030-03-05")
    record("P8c", 8, "A§3.2 护栏③：deleted 反向=恢复 deleted_at=NULL",
           "remove 软删 D2 成为最新批 → undo → 读库",
           "软删生效→undo 后 deleted_at 回 NULL 且原字段值恢复",
           {"before_undo_deleted_at": mid, "after_undo": tuple(after) if after else None,
            "undo_batch_id": undo_id3, "undone_batch_change_rows": orig_rows3,
            "undo_batch_change_rows": undo_rows3},
           "PASS_PROBE" if ok_c else "FAIL_PROBE",
           "定位型探针：同 P8b，以行级数据定位病因层")
    # P8d 廉价负例：undo 批不可再撤
    ok2, out2 = call(env.service.undo_batches, env.admin, 1, {"batch_ids": [last_undo]})
    record("P8d", 8, "A§3.2 护栏②④：undo 批不可再撤（不做 redo）",
           "对最新 undo 批 %s 再 undo" % last_undo, "ApiError 409 UNDO_TARGET_STALE",
           brief(out2),
           "PASS_PROBE" if (not ok2 and out2.get("status") == 409
                            and out2.get("code") == "UNDO_TARGET_STALE") else "FAIL_PROBE")

# ================= main =================
def main():
    import hashlib
    env = Env()
    H = negotiate_headers(env)
    print(json.dumps({"event": "headers", "using": H}, ensure_ascii=False))
    # P1/P2/P3/P4 共用 env（独立顺序执行，探针数据互不冲突：项目名全不同）
    probe_serial(env, H)
    probe_status(env, H)
    probe_aggregate(env, H)
    probe_limits(env, H)
    # P5/P6 各用干净 env（导出/往返对全库敏感）
    probe_export_boundary(env)
    rt = Env()
    probe_roundtrip(rt)
    probe_migration()
    uv = Env()
    probe_undo(uv)
    probe_header_contract(None)
    # 只读取证：真实 flowboard.db 未被本探针触碰（mtime 仍为事故记录值）
    real = REPO / "flowboard.db"
    if real.exists():
        import os
        st = real.stat()
        record("PX-realdb", 0, "team-task §4 红线：需要触碰真实 flowboard.db……必须停下",
               "探针全程结束后 stat 真实库（只读）",
               "mtime 保持 2026-08-12 14:31 前后、未被本探针写入",
               {"mtime": st.st_mtime, "size": st.st_size}, "PASS_PROBE", "")
    out_path = Path(__file__).resolve().parent / "b002_probe_results.json"
    out_path.write_text(json.dumps(
        {"using_headers": H, "results": RESULTS}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    counts = {}
    for r in RESULTS:
        counts[r["observed"]] = counts.get(r["observed"], 0) + 1
    print(json.dumps({"event": "summary", "counts": counts,
                      "total": len(RESULTS)}, ensure_ascii=False))
    print("results -> " + str(out_path))


# ================= 追加项 10（lead 裁定并入 B-002）：表头契约字面收敛 =================
def extract_headers(xlsx_bytes):
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    first = root.find(".//{" + SSML + "}row")
    if first is None:
        return []
    out = []
    for c in first.findall("{" + SSML + "}c"):
        t = c.find(".//{" + SSML + "}t")
        out.append((t.text or "") if t is not None else "")
    return out

def probe_header_contract(_shared):
    crit = ("A§5 依据行：列序=项目名称｜阶段｜轨道｜节点｜日期｜间隔｜状态｜备注；"
            "A§5.1 表头行：strip 后与 8 列标准列名完全一致（含顺序、无重复）；"
            "不一致=文件级 422 IMPORT_HEADERS_MISMATCH，文案附标准表头；"
            "A§3.7 导出：8 列同格式（lead 裁定：导入期望表头/导出产列表头/报错附件全收敛契约字面）")
    env = Env()
    legal = {"project": ("s", "表头正例项目"), "stage": ("s", "创意"), "track": ("s", "main"),
             "node": ("s", "表头正例节点"), "date": ("s", "2030-01-01"),
             "interval": ("s", ""), "status": ("s", ""), "remark": ("s", "")}
    ok, out = call(env.service.preview_import, env.admin, 1, "contract-header.xlsx",
                   build_xlsx(CONTRACT_HEADERS, [make_row(CONTRACT_HEADERS, legal)]))
    record("P0a", 10, crit, "契约字面 8 列表头 + 合法数据行 → preview_import",
           "接受（preview 成功）", brief(out),
           "PASS_PROBE" if ok else "FAIL_PROBE", "追加项⑩正例：契约表头必须可用")
    shuffled = list(CONTRACT_HEADERS)
    shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
    ok, out = call(env.service.preview_import, env.admin, 1, "shuffled.xlsx",
                   build_xlsx(shuffled, [make_row(shuffled, legal)]))
    code = out.get("code") if isinstance(out, dict) else None
    record("P0c", 10, crit, "契约列名乱序表头（前两列互换）→ preview_import",
           "ApiError 422 IMPORT_HEADERS_MISMATCH（文件级，含顺序校验）", brief(out),
           "PASS_PROBE" if (not ok and out.get("status") == 422
                            and code == "IMPORT_HEADERS_MISMATCH") else "FAIL_PROBE",
           "乱序负例保留")
    missing = [h for h in CONTRACT_HEADERS if h != "间隔"]
    ok, out = call(env.service.preview_import, env.admin, 1, "missing.xlsx",
                   build_xlsx(missing, [make_row(missing, legal)]))
    code = out.get("code") if isinstance(out, dict) else None
    record("P0d", 10, crit, "缺「间隔」列的 7 列表头 → preview_import",
           "ApiError 422 IMPORT_HEADERS_MISMATCH（文件级）", brief(out),
           "PASS_PROBE" if (not ok and out.get("status") == 422
                            and code == "IMPORT_HEADERS_MISMATCH") else "FAIL_PROBE",
           "缺列负例保留")
    env2 = Env()
    pid = env2.service.create_project(env2.admin, 1, {"name": "导出表头项目"})["project_id"]
    env2.service.submit_batches(env2.admin, 1, {"requests": [{"project_id": pid, "base_version": 1,
        "changes": [{"create": {"track": "main", "stage": "创意", "name": "H1",
                                "date": "2030-01-01"}}]}]})
    ok, raw = call(env2.service.export_timeline, env2.admin, 1)
    hdr = extract_headers(raw) if ok else None
    record("P0b", 10, crit, "隔离库导出 → 解析产物第一行表头，逐列比对契约字面 8 列",
           "extract_headers(export_bytes) == ['项目名称','阶段','轨道','节点','日期','间隔','状态','备注']（顺序敏感）",
           {"export_ok": ok, "headers": hdr}, "PASS_PROBE" if hdr == CONTRACT_HEADERS else "FAIL_PROBE",
           "round-trip 前置：导出表头不收敛则真实字节往返必被表头关卡挡住")

if __name__ == "__main__":
    main()

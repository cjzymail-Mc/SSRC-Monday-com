"""One native XLSX layout for timeline exports and the downloadable example template.

Uses the application's existing standard-library OOXML approach, so the local
server needs no office installation or additional runtime dependencies.
"""
import io
import math
import unicodedata
import zipfile
from datetime import date
from xml.etree import ElementTree as ET

from .transfer import MAX_ROWS, safe_cell


HEADERS = ["项目名称", "阶段", "主线/并行", "节点", "日期", "状态", "备注"]
STAGES = ("创意", "设计", "开发", "测试", "量产", "应用迭代")
WIDTHS = (25, 16, 14, 32, 16, 16, 44)
DATE_MIN = date(1950, 1, 1)
DATE_MAX = date(2100, 1, 1)
EPOCH = date(1899, 12, 30)
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Fictional, importable examples belong only to the template, never to exports.
TEMPLATE_ROWS = (
    ("示例A-新品开发", "创意", "主线", "项目立项", "2026-10-01", "已完成", "明确产品定位与交付范围"),
    ("示例A-新品开发", "设计", "主线", "设计定稿", "2026-10-12", "", "完成外观与结构评审"),
    ("示例A-新品开发", "开发", "主线", "样品完成", "2026-10-26", "", "提交可测试样品"),
    ("示例A-新品开发", "测试", "并行", "材料验证", "2026-10-28", "", "并行验证材料耐久性"),
    ("示例A-新品开发", "测试", "主线", "测试验收", "2026-11-06", "", "完成测试并关闭问题"),
    ("示例A-新品开发", "量产", "主线", "量产启动", "2026-11-20", "未开始", "确认生产工艺与质量标准"),
    ("示例A-新品开发", "应用迭代", "主线", "首轮复盘", "2026-12-04", "未开始", "收集使用反馈并安排改进"),
    ("示例B-包装改版", "创意", "主线", "改版立项", "2026-10-05", "已完成", "确认包装规格与预算"),
    ("示例B-包装改版", "设计", "主线", "包装定稿", "2026-10-15", "", "确认版式与印刷文件"),
    ("示例B-包装改版", "测试", "并行", "运输测试", "2026-10-22", "", "验证包装保护性能"),
    ("示例B-包装改版", "量产", "主线", "批量切换", "2026-11-02", "未开始", "新旧包装切换完成"),
    ("示例C-应用升级", "设计", "主线", "需求确认", "2026-10-08", "已完成", "明确升级范围与验收口径"),
    ("示例C-应用升级", "开发", "主线", "功能开发完成", "2026-10-23", "", "交付测试版本"),
    ("示例C-应用升级", "测试", "主线", "回归验收", "2026-10-30", "", "关键流程全部通过"),
    ("示例C-应用升级", "应用迭代", "主线", "发布复盘", "2026-11-12", "未开始", "整理用户反馈与下一轮计划"),
)
INSTRUCTIONS_LAST_ROW = 30


def _element(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {key: str(value) for key, value in attrs.items()})


def _xml(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _cell(row, column, value, style, *, as_date=False):
    cell = _element(row, "c", r=f"{column}{row.get('r')}", s=style)
    if as_date and value:
        parsed = date.fromisoformat(value)
        # Text dates outside the numeric import range remain lossless on export.
        if DATE_MIN <= parsed <= DATE_MAX:
            _element(cell, "v").text = str((parsed - EPOCH).days)
            return
    if value != "" and value is not None:
        cell.set("t", "inlineStr")
        text = _element(_element(cell, "is"), "t")
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text.text = safe_cell(value)


def _height(values, widths=WIDTHS):
    def lines(text, width):
        return sum(max(1, math.ceil(sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in line) / (width - 2)))
                   for line in str(text).split("\n"))
    return min(409, max(34, max(lines(value, width) for value, width in zip(values, widths)) * 15 + 8))


def _sheet(widths, last_row, freeze=1):
    sheet = ET.Element("worksheet", xmlns=NS)
    _element(sheet, "dimension", ref=f"A1:G{last_row}")
    view = _element(_element(sheet, "sheetViews"), "sheetView", workbookViewId=0, showGridLines=0, zoomScale=90)
    _element(view, "pane", ySplit=freeze, topLeftCell=f"A{freeze + 1}", activePane="bottomLeft", state="frozen")
    _element(view, "selection", pane="bottomLeft", activeCell=f"A{freeze + 1}", sqref=f"A{freeze + 1}")
    _element(sheet, "sheetFormatPr", defaultRowHeight=34)
    cols = _element(sheet, "cols")
    for index, width in enumerate(widths, 1):
        _element(cols, "col", min=index, max=index, width=width, customWidth=1)
    return sheet


def _styles():
    root = ET.Element("styleSheet", xmlns=NS)
    _element(_element(root, "numFmts", count=1), "numFmt", numFmtId=164, formatCode="yyyy-mm-dd")
    fonts = _element(root, "fonts", count=4)
    for size, color, bold in ((10, "17233C", False), (11, "FFFFFF", True), (18, "FFFFFF", True), (11, "344054", False)):
        font = _element(fonts, "font")
        _element(font, "sz", val=size)
        _element(font, "color", rgb="FF" + color)
        _element(font, "name", val="Microsoft YaHei")
        if bold:
            _element(font, "b")
    fills = _element(root, "fills", count=5)
    for kind, color in (("none", None), ("gray125", None), ("solid", "243B64"), ("solid", "FFFFFF"), ("solid", "F7F9FC")):
        fill = _element(_element(fills, "fill"), "patternFill", patternType=kind)
        if color:
            _element(fill, "fgColor", rgb="FF" + color)
    borders = _element(root, "borders", count=2)
    _element(borders, "border")
    border = _element(borders, "border")
    for edge in ("left", "right", "top", "bottom"):
        _element(_element(border, edge, style="thin"), "color", rgb="FFD8DEE8")
    _element(_element(root, "cellStyleXfs", count=1), "xf", numFmtId=0, fontId=0, fillId=0, borderId=0)
    xfs = _element(root, "cellXfs", count=8)
    # 0 default, 1 header, 2 wrapped body, 3 centered body, 4 date,
    # 5 instructions title, 6 instructions prose, 7 alternate instructions row.
    for font, fill, border, number, align, wrap in (
        (0, 0, 0, 0, "left", False), (1, 2, 1, 0, "center", True),
        (0, 3, 1, 0, "left", True), (0, 3, 1, 0, "center", True),
        (0, 3, 1, 164, "center", False), (2, 2, 0, 0, "left", True),
        (3, 3, 0, 0, "left", True), (0, 4, 1, 0, "left", True),
    ):
        xf = _element(xfs, "xf", numFmtId=number, fontId=font, fillId=fill, borderId=border, xfId=0,
                      applyNumberFormat=1, applyFont=1, applyFill=1, applyBorder=1, applyAlignment=1)
        _element(xf, "alignment", horizontal=align, vertical="center", wrapText=int(wrap))
    _element(_element(root, "cellStyles", count=1), "cellStyle", name="Normal", xfId=0, builtinId=0)
    dxfs = _element(root, "dxfs", count=7)
    for color, kind in (("EEF4FF", "fill"), ("ECFDF8", "fill"), ("2457B8", "font"), ("078C6C", "font"),
                        ("16803C", "font"), ("B54708", "font"), ("667085", "font")):
        dxf = _element(dxfs, "dxf")
        if kind == "fill":
            _element(_element(_element(dxf, "fill"), "patternFill", patternType="solid"), "fgColor", rgb="FF" + color)
        else:
            font = _element(dxf, "font")
            _element(font, "b")
            _element(font, "color", rgb="FF" + color)
    return _xml(root)


def _timeline_sheet(rows):
    # Match the existing 300-row writing template; validations also cover rows
    # added later, all the way to the importer/exporter's common 1000-row limit.
    last_row = max(301, len(rows) + 1)
    sheet = _sheet(WIDTHS, last_row)
    data = _element(sheet, "sheetData")
    header = _element(data, "row", r=1, ht=30, customHeight=1)
    for column, value in zip("ABCDEFG", HEADERS):
        _cell(header, column, value, 1)
    for index in range(2, last_row + 1):
        values = rows[index - 2] if index - 2 < len(rows) else [""] * 7
        row = _element(data, "row", r=index, ht=_height(values), customHeight=1)
        for column, value, style in zip("ABCDEFG", values, (2, 3, 3, 2, 4, 3, 2)):
            _cell(row, column, value, style, as_date=column == "E")
    _element(sheet, "autoFilter", ref=f"A1:G{last_row}")
    end = MAX_ROWS + 1
    for priority, (area, formula) in enumerate((
        (f"A2:G{end}", '$C2="主线"'), (f"A2:G{end}", '$C2="并行"'),
        (f"C2:C{end}", '$C2="主线"'), (f"C2:C{end}", '$C2="并行"'),
        (f"F2:F{end}", '$F2="已完成"'), (f"F2:F{end}", '$F2="进行中"'), (f"F2:F{end}", '$F2="未开始"'),
    ), 1):
        rule = _element(_element(sheet, "conditionalFormatting", sqref=area), "cfRule",
                        type="expression", dxfId=priority - 1, priority=priority)
        _element(rule, "formula").text = formula
    validations = _element(sheet, "dataValidations", count=7)
    for column, kind, operator, first, second, allow_blank, message in (
        ("A", "textLength", "lessThanOrEqual", "200", None, False, "项目名称最多 200 个字符，每行都要填写。"),
        ("B", "list", None, '"' + ",".join(STAGES) + '"', None, False, "请选择列表中的项目阶段。"),
        ("C", "list", None, '"主线,并行"', None, False, "请选择主线或并行。"),
        ("D", "textLength", "lessThanOrEqual", "500", None, False, "节点名称最多 500 个字符。"),
        ("E", "date", "between", str((DATE_MIN - EPOCH).days), str((DATE_MAX - EPOCH).days), False, "请输入 1950-01-01 至 2100-01-01 的日期。"),
        ("F", "list", None, '"未开始,进行中,已完成"', None, True, "请选择未开始、进行中、已完成，或留空。"),
        ("G", "textLength", "lessThanOrEqual", "500", None, True, "备注最多 500 个字符。"),
    ):
        validation = _element(validations, "dataValidation", type=kind, sqref=f"{column}2:{column}{end}",
                              allowBlank=int(allow_blank), showInputMessage=1, showErrorMessage=1,
                              errorStyle="stop", errorTitle="请检查填写内容", error=message, promptTitle=HEADERS[ord(column) - 65], prompt=message)
        if operator:
            validation.set("operator", operator)
        _element(validation, "formula1").text = first
        if second:
            _element(validation, "formula2").text = second
    _element(sheet, "pageMargins", left=0.25, right=0.25, top=0.5, bottom=0.5, header=0.2, footer=0.2)
    _element(sheet, "pageSetup", paperSize=9, orientation="landscape", fitToWidth=1, fitToHeight=0)
    return _xml(sheet)


def _instructions_sheet():
    widths = (18, 16, 28, 32, 16, 16, 44)
    sheet = _sheet(widths, INSTRUCTIONS_LAST_ROW, freeze=1)
    data = _element(sheet, "sheetData")
    merges = []

    def line(number, values, style=6, height=34, merge=None):
        row = _element(data, "row", r=number, ht=height, customHeight=1)
        for column, value in zip("ABCDEFG", values):
            _cell(row, column, value, style)
        if merge:
            merges.append(merge)

    line(1, ["Flowboard 项目时间表填写说明"], style=5, height=42, merge="A1:G1")
    line(2, [f"下载的模板在 Timeline 第 2–{len(TEMPLATE_ROWS) + 1} 行预置 3 个虚构项目、{len(TEMPLATE_ROWS)} 个节点，演示主线、并行、阶段、日期、状态和备注。"], height=42, merge="A2:G2")
    line(3, ["正式使用前请替换或清除全部示例内容，保留表头和格式。保留的示例行会作为真实项目导入，示例日期请按实际计划修改。"], height=42, merge="A3:G3")
    line(5, ["【单项目】只导入一个项目"], style=1, merge="A5:G5")
    line(6, ["保留一组示例并改成真实数据，清除另外两组。也可清空第 2 行起的内容，再从第 2 行填写。"], merge="A6:G6")
    line(7, ["每行填写同一个项目名称，一个节点占一行。按实际计划填写主线或并行节点，预览应显示“1 个项目”。"], merge="A7:G7")
    line(9, ["【多项目】在同一张表导入多个项目"], style=1, merge="A9:G9")
    line(10, ["在 Timeline 中连续填写不同项目。每行都填写所属项目名称，同一项目名称保持一致，不合并单元格。"], merge="A10:G10")
    line(11, ["无需为每个项目建立 Sheet。系统按项目名称归组，请在预览中逐项核对项目名称和节点数，再点击提交。"], merge="A11:G11")
    line(13, ["工作表选择与导入"], style=1, merge="A13:G13")
    line(14, ["保存为 .xlsx，在“我的工作”点击“导入 Excel”或拖入文件，选择 Timeline 工作表，预览通过后手动提交。"], merge="A14:G14")
    line(15, ["一次只导入所选 Sheet，不自动合并其他工作表。“填写说明”不作为数据表；若项目分散在多张表，需分别选择并导入。"], height=42, merge="A15:G15")
    line(16, ["导入只创建新项目，不能更新已有项目的节点。同名已有项目会报错；修改已有节点请进入时间表编辑器。"], merge="A16:G16")
    line(18, ["字段", "是否必填", "允许值 / 格式", "填写说明"], style=1, merge="D18:G18")
    fields = (
        ("项目名称", "必填", "文本，最多 200 字", "同一项目的节点使用同一名称；多个项目直接接着往下填，无需新建工作表。"),
        ("阶段", "必填", " / ".join(STAGES), "请从下拉列表选择阶段。"),
        ("主线/并行", "必填", "主线 / 并行", "主线行显示浅蓝色，并行行显示浅绿色；更改轨道后颜色自动更新。"),
        ("节点", "必填", "文本，最多 500 字", "填写清晰、可验收的里程碑名称。"),
        ("日期", "必填", "YYYY-MM-DD", "填写 Excel 日期；数值日期范围为 1950-01-01 至 2100-01-01。"),
        ("状态", "可选", "未开始 / 进行中 / 已完成", "仅“已完成”保留，其余状态或留空会在导入后按日期重算。"),
        ("备注", "可选", "文本，最多 500 字", "填写交付物、验收口径或补充说明；不使用公式、宏或外部链接。"),
    )
    for number, values in enumerate(fields, 19):
        line(number, values, style=2 if number % 2 == 0 else 7, height=52, merge=f"D{number}:G{number}")
    line(27, ["间隔由系统按日期自动计算。标准格式不含间隔列，仍兼容旧八列模板，旧间隔列导入时忽略。"], merge="A27:G27")
    line(28, [f"单文件最多 {MAX_ROWS} 条节点、1.5 MB。不要增加标题行、修改或调换七列表头，不填写公式、宏或外部链接。"], merge="A28:G28")
    line(29, ["清除示例时请清空整行七列的内容。只删项目名而保留其他单元格，会产生不完整数据并导致校验失败。"], merge="A29:G29")
    line(30, ["导出只包含工作区未删除、未归档项目的实际节点，不添加示例。导出文件不包含标签、历史记录等完整备份信息。"], height=42, merge="A30:G30")
    merge_cells = _element(sheet, "mergeCells", count=len(merges))
    for area in merges:
        _element(merge_cells, "mergeCell", ref=area)
    return _xml(sheet)


def make_timeline_xlsx(rows):
    """Render exactly the supplied seven-column rows, including empty exports."""
    rows = list(rows)
    if len(rows) > MAX_ROWS:
        raise ValueError("Timeline exceeds the shared 1000-row limit")
    workbook = ET.Element("workbook", xmlns=NS, attrib={"xmlns:r": DOC_REL_NS})
    _element(_element(workbook, "bookViews"), "workbookView", activeTab=0)
    sheets = _element(workbook, "sheets")
    for index, name in enumerate(("Timeline", "填写说明"), 1):
        _element(sheets, "sheet", name=name, sheetId=index, **{"r:id": f"rId{index}"})
    defined = _element(workbook, "definedNames")
    if rows:
        _element(defined, "definedName", name="_xlnm.Print_Area", localSheetId=0).text = f"Timeline!$A$1:$G${len(rows) + 1}"
    _element(defined, "definedName", name="_xlnm.Print_Titles", localSheetId=0).text = "Timeline!$1:$1"
    _element(defined, "definedName", name="_xlnm.Print_Area", localSheetId=1).text = f"'填写说明'!$A$1:$G${INSTRUCTIONS_LAST_ROW}"
    rels = ET.Element("Relationships", xmlns=REL_NS)
    for index, target in enumerate(("worksheets/sheet1.xml", "worksheets/sheet2.xml", "styles.xml"), 1):
        _element(rels, "Relationship", Id=f"rId{index}", Type=f"{DOC_REL_NS}/{'styles' if index == 3 else 'worksheet'}", Target=target)
    root_rels = ET.Element("Relationships", xmlns=REL_NS)
    _element(root_rels, "Relationship", Id="rId1", Type=f"{DOC_REL_NS}/officeDocument", Target="xl/workbook.xml")
    types = ET.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
    _element(types, "Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    _element(types, "Default", Extension="xml", ContentType="application/xml")
    for path, kind in (("workbook.xml", "sheet.main"), ("styles.xml", "styles"), ("worksheets/sheet1.xml", "worksheet"), ("worksheets/sheet2.xml", "worksheet")):
        _element(types, "Override", PartName="/xl/" + path, ContentType=f"application/vnd.openxmlformats-officedocument.spreadsheetml.{kind}+xml")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, raw in (("[Content_Types].xml", _xml(types)), ("_rels/.rels", _xml(root_rels)),
                          ("xl/workbook.xml", _xml(workbook)), ("xl/_rels/workbook.xml.rels", _xml(rels)),
                          ("xl/styles.xml", _styles()), ("xl/worksheets/sheet1.xml", _timeline_sheet(rows)),
                          ("xl/worksheets/sheet2.xml", _instructions_sheet())):
            archive.writestr(path, raw)
    return output.getvalue()


def make_timeline_template():
    return make_timeline_xlsx(TEMPLATE_ROWS)

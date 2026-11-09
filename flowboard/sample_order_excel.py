"""Original-template signed Excel and annual statistics for sample orders."""
import io
import json
import re
import zipfile
from datetime import date
from html import escape as html_escape

def xml(value):
    return html_escape(str(value), quote=True)


def set_cell(source, address, value):
    start = source.find(f'<c r="{address}"')
    if start < 0:
        raise ValueError(f"原始模板缺少单元格 {address}")
    opening_end = source.find(">", start)
    if opening_end < 0:
        raise ValueError("原始模板单元格结构无效")
    end = opening_end + 1 if source[opening_end - 1] == "/" else source.find("</c>", opening_end) + 4
    if end < opening_end:
        raise ValueError("原始模板单元格结构无效")
    original = source[start:end]
    style = re.search(r'\bs="(\d+)"', original)
    prefix = f'<c r="{address}"' + (f' s="{style.group(1)}"' if style else "")
    if value is None or value == "":
        replacement = prefix + "/>"
    elif isinstance(value, (int, float)):
        replacement = prefix + f"><v>{value}</v></c>"
    else:
        replacement = prefix + f' t="inlineStr"><is><t xml:space="preserve">{xml(value)}</t></is></c>'
    return source[:start] + replacement + source[end:]


def shifted_row(row_xml, delta):
    return re.sub(r'\br="([A-Z]*)(\d+)"', lambda match: f'r="{match.group(1)}{int(match.group(2)) + delta}"', row_xml)


def excel_date(value):
    return (date.fromisoformat(value) - date(1899, 12, 30)).days if value else None


def make_sheet(source, order):
    items = order["items"]
    count = len(items)
    delta = count - 5
    last_row = count + 6
    match = re.search(r'<sheetData>([\s\S]*?)</sheetData>', source)
    if not match:
        raise ValueError("原始模板缺少工作表数据")
    rows = re.findall(r'<row\b[^>]*(?:/>|>[\s\S]*?</row>)', match.group(1))
    if len(rows) != 24:
        raise ValueError("原始模板行结构已变更")
    by_number = {int(re.match(r'<row r="(\d+)"', row).group(1)): row for row in rows}
    rebuilt = [by_number[n] for n in range(1, 5)]
    rebuilt += [by_number[n] for n in range(5, min(5 + count, 10))]
    rebuilt += [shifted_row(by_number[9], n - 9) for n in range(10, 5 + count)]
    rebuilt += [shifted_row(by_number[10], delta), shifted_row(by_number[11], delta)]

    def trim_columns(row):
        row = re.sub(r'<c r="([A-Z]+)\d+"[^>]*(?:/>|>[\s\S]*?</c>)',
                     lambda m: m.group(0) if len(m.group(1)) == 1 and m.group(1) <= "L" else "", row)
        return re.sub(r'\bspans="\d+:\d+"', 'spans="1:12"', row)

    sheet = source[:match.start()] + '<sheetData>' + ''.join(trim_columns(row) for row in rebuilt) + '</sheetData>' + source[match.end():]
    sheet = re.sub(r'<dimension ref="[^"]+"/>', f'<dimension ref="A1:L{last_row}"/>', sheet, count=1)
    sheet = re.sub(r'<cols>[\s\S]*?</cols>', lambda m: '<cols>' + ''.join(
        re.sub(r'max="\d+"', 'max="12"', col) if int(re.search(r'max="(\d+)"', col).group(1)) > 12 else col
        for col in re.findall(r'<col\b[^>]*/>', m.group(0))
        if int(re.search(r'min="(\d+)"', col).group(1)) <= 12
    ) + '</cols>', sheet, count=1)
    sheet = sheet.replace('<f ca="1">A1:L11</f>', f'<f ca="1">A1:L{last_row}</f>')
    sheet = sheet.replace('activeCell="B9" sqref="B9"', 'activeCell="B5" sqref="B5"')

    def ref_shift(text):
        return re.sub(r'([A-Z]+)(\d+)', lambda m: m.group(1) + str(int(m.group(2)) + (delta if int(m.group(2)) >= 10 else 0)), text)
    for tag in ("mergeCell", "protectedRange", "conditionalFormatting"):
        sheet = re.sub(r'(<'+tag+r'\b[^>]*\b(?:ref|sqref)=")([^"]+)(")', lambda m: m.group(1)+ref_shift(m.group(2))+m.group(3), sheet)
    sheet = set_cell(sheet, "K3", "编号：" + order["number"])
    for i, item in enumerate(items):
        row = i + 5
        values = {
            "A": i + 1 if item else None,
            "B": item["style"] + item["category"] if item else None,
            "C": item["sole"] if item else None,
            "D": item["gender"] if item else None,
            "F": item["color"] if item else None,
            "G": item["quantity"] if item else None,
            "H": item["size"] if item else None,
            "I": item["purpose"] if item else None,
            "J": excel_date(item["due_date"]) if item else None,
            "L": item["remark"] if item else None,
        }
        for col, value in values.items():
            sheet = set_cell(sheet, f"{col}{row}", value)
    sheet = set_cell(sheet, f"G{count + 5}", sum(item["quantity"] for item in items))
    return sheet


def photo_anchor(source, row, rel_id, unique_id):
    anchor_index = 0 if row <= 6 else min(row - 6, 3)
    sample_row = anchor_index + 6
    anchor = source[anchor_index]
    anchor = re.sub(r'<xdr:row>\d+</xdr:row>', f'<xdr:row>{row - 1}</xdr:row>', anchor)
    anchor = re.sub(r'r:embed="rId\d+"', f'r:embed="{rel_id}"', anchor, count=1)
    anchor = re.sub(r'(<xdr:cNvPr id=")\d+(" name=")[^"]*(")', lambda m: m.group(1)+str(unique_id)+m.group(2)+f'鞋款图片 {row - 4}'+m.group(3), anchor, count=1)
    delta = row - sample_row
    if delta:
        anchor = re.sub(r'(<a:off x="\d+" y=")(\d+)(")', lambda m: m.group(1)+str(int(m.group(2)) + delta*1228725)+m.group(3), anchor, count=1)
    return anchor


def signed_workbook(order, template_bytes, anchors, uploads):
    with zipfile.ZipFile(io.BytesIO(template_bytes)) as src:
        files = {info.filename: (info, src.read(info.filename)) for info in src.infolist()}
    sheet_key = "xl/worksheets/sheet1.xml"
    drawing_key = "xl/drawings/drawing1.xml"
    rels_key = "xl/drawings/_rels/drawing1.xml.rels"
    files[sheet_key] = (files[sheet_key][0], make_sheet(files[sheet_key][1].decode(), order).encode())
    drawing = files[drawing_key][1].decode()
    rels = files[rels_key][1].decode()
    new_anchors = []
    needs_jpeg = False
    next_rel = 2
    for i, item in enumerate(order["items"]):
        name = item["photo_file"]
        if not name:
            continue
        extension = name.rsplit(".", 1)[1]
        media_name = f'order_photo_{i + 1}.{extension}'
        new_anchors.append(photo_anchor(anchors, i + 5, f'rId{next_rel}', 100+i))
        rels = rels.replace('</Relationships>', f'<Relationship Id="rId{next_rel}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{media_name}"/></Relationships>')
        files[f'xl/media/{media_name}'] = (None, (uploads / name).read_bytes())
        needs_jpeg |= extension == "jpg"
        next_rel += 1
    files[drawing_key] = (files[drawing_key][0], drawing.replace('</xdr:wsDr>', ''.join(new_anchors) + '</xdr:wsDr>').encode())
    files[rels_key] = (files[rels_key][0], rels.encode())
    if needs_jpeg:
        key = "[Content_Types].xml"
        types = files[key][1].decode()
        if 'Extension="jpg"' not in types:
            types = types.replace('</Types>', '<Default Extension="jpg" ContentType="image/jpeg"/></Types>')
        files[key] = (files[key][0], types.encode())
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as dest:
        for name, (info, payload) in files.items():
            dest.writestr(info or name, payload)
    return out.getvalue()


def annual_workbook(year, orders):
    selected = [order for order in orders if order["order_date"].startswith(str(year)) and order["status"] == "已下单"]
    grouped = {}
    details = []
    for order in selected:
        for item in order["items"]:
            group = grouped.setdefault(item["category"] or "未分类", {"styles": set(), "pairs": 0})
            group["styles"].add(item["style"])
            group["pairs"] += item["quantity"]
            details.append([order["number"], order["order_date"], item.get("contractor", order["contractor"]), order["handover_status"], order["receiver"], item["style"], item["category"], item["sole"], item["gender"], item["color"], item["quantity"], item["size"], item["purpose"], item["due_date"], item["remark"]])
    summary = [["品类", "不同款号（款）", "数量（双）"]]
    summary += [[category, len(value["styles"]), value["pairs"]] for category, value in sorted(grouped.items(), key=lambda kv: -kv[1]["pairs"])]
    summary.append(["合计", len({item["style"] for order in selected for item in order["items"]}), sum(item["quantity"] for order in selected for item in order["items"])])
    detail = [["需求单编号", "申请日期", "承接单位", "交接状态", "接收人", "款号", "品类", "底模号", "性别", "配色", "数量（双）", "号码", "用途说明", "需求时间", "备注"]] + details

    def sheet_xml(rows, widths):
        cols = ''.join(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>' for i, width in enumerate(widths, 1))
        lines = []
        for ri, cells in enumerate(rows, 1):
            parts = []
            for ci, value in enumerate(cells, 1):
                col = ""
                n = ci
                while n:
                    n, rem = divmod(n - 1, 26)
                    col = chr(65 + rem) + col
                address = f"{col}{ri}"
                style = ' s="1"' if ri == 1 else ""
                if isinstance(value, (int, float)):
                    parts.append(f'<c r="{address}"{style}><v>{value}</v></c>')
                else:
                    parts.append(f'<c r="{address}"{style} t="inlineStr"><is><t>{xml(value)}</t></is></c>')
            lines.append(f'<row r="{ri}">'+''.join(parts)+'</row>')
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<cols>{cols}</cols><sheetData>{"".join(lines)}</sheetData>'
                f'<autoFilter ref="A1:{"C" if len(widths)==3 else "O"}{len(rows)}"/>'
                '</worksheet>').encode()

    files = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="年度汇总" sheetId="1" r:id="rId1"/><sheet name="下单明细" sheetId="2" r:id="rId2"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="10"/><name val="Microsoft YaHei"/></font><font><b/><sz val="10"/><name val="Microsoft YaHei"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEAF1F1"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        'xl/worksheets/sheet1.xml': sheet_xml(summary, [22, 20, 18]),
        'xl/worksheets/sheet2.xml': sheet_xml(detail, [20, 14, 14, 14, 16, 22, 14, 16, 9, 16, 13, 13, 32, 14, 32]),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as dest:
        for name, content in files.items():
            dest.writestr(name, content.encode() if isinstance(content, str) else content)
    return out.getvalue()

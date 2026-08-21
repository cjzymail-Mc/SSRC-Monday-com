"""Bounded CSV/XLSX parsing and generation; never evaluates spreadsheet formulas."""
import csv
import io
import re
import zipfile
from xml.etree import ElementTree as ET

MAX_FILE_BYTES=1_500_000
MAX_ROWS=1000
MAX_COLUMNS=100
MAX_CELL_LENGTH=10_000
MAX_ZIP_ENTRIES=200
MAX_UNCOMPRESSED=12_000_000
NS="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class XlsxNumericCell(str):
    """String-compatible marker retaining whether an OOXML cell was numeric."""

class TransferError(Exception):
    def __init__(self,code,message,details=None):super().__init__(message);self.code=code;self.message=message;self.details=details or {}

def _check_table(rows):
    if not rows or not any(any(str(cell).strip() for cell in row) for row in rows):raise TransferError("IMPORT_EMPTY","文件没有可导入数据")
    width=max(len(row) for row in rows)
    if width>MAX_COLUMNS:raise TransferError("IMPORT_TOO_MANY_COLUMNS","列数超过限制",{"max":MAX_COLUMNS})
    normalized=[]
    for row_index,row in enumerate(rows[:MAX_ROWS+2],1):
        values=[]
        for column_index,value in enumerate(row,1):
            text="" if value is None else (value if isinstance(value, XlsxNumericCell) else str(value))
            if len(text)>MAX_CELL_LENGTH:raise TransferError("IMPORT_CELL_TOO_LONG","单元格内容超过限制",{"row":row_index,"column":column_index,"max":MAX_CELL_LENGTH})
            values.append(text)
        normalized.append(values+[""]*(width-len(values)))
    if len(normalized)-1>MAX_ROWS:raise TransferError("IMPORT_TOO_MANY_ROWS","数据行数超过限制",{"max":MAX_ROWS})
    headers=[item.strip() for item in normalized[0]]
    if any(not item for item in headers):raise TransferError("IMPORT_EMPTY_HEADER","表头不能为空")
    folded=[item.casefold() for item in headers]
    duplicates=sorted({item for item in folded if folded.count(item)>1})
    if duplicates:raise TransferError("IMPORT_DUPLICATE_HEADER","表头不能重复",{"headers":duplicates})
    data=[row for row in normalized[1:] if any(cell.strip() for cell in row)]
    return headers,data

def _decode_csv(raw):
    for encoding in ("utf-8-sig","gb18030"):
        try:return raw.decode(encoding),encoding
        except UnicodeDecodeError:pass
    raise TransferError("IMPORT_ENCODING_UNSUPPORTED","CSV 编码无法识别，仅支持 UTF-8 BOM/UTF-8/GB18030")

def parse_csv(raw):
    text,encoding=_decode_csv(raw)
    try:rows=list(csv.reader(io.StringIO(text,newline="")))
    except csv.Error as error:raise TransferError("IMPORT_CSV_INVALID","CSV 格式无效",{"reason":str(error)})
    headers,data=_check_table(rows)
    return {"format":"csv","encoding":encoding,"sheet":"CSV","headers":headers,"rows":data}

def _xlsx_cell(cell,shared):
    if cell.find(NS+"f") is not None:raise TransferError("IMPORT_FORMULA_FORBIDDEN","Excel 公式不允许导入")
    kind=cell.get("t");value=cell.find(NS+"v")
    if kind=="inlineStr":return "".join(node.text or "" for node in cell.findall(".//"+NS+"t"))
    raw=value.text if value is not None and value.text is not None else ""
    if kind=="s":
        try:return shared[int(raw)]
        except (ValueError,IndexError):raise TransferError("IMPORT_XLSX_INVALID","共享字符串索引无效")
    if kind=="b":return "true" if raw=="1" else "false"
    return XlsxNumericCell(raw) if kind in (None,"n") and raw != "" else raw

def parse_xlsx(raw,sheet_name=None):
    try:z=zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile,OSError):raise TransferError("IMPORT_XLSX_INVALID","Excel 文件无效")
    with z:
        infos=z.infolist()
        if len(infos)>MAX_ZIP_ENTRIES or sum(item.file_size for item in infos)>MAX_UNCOMPRESSED:raise TransferError("IMPORT_XLSX_BOMB","Excel 压缩内容超过安全限制")
        names={item.filename for item in infos}
        if any(name.lower().endswith("vbaproject.bin") or name.startswith("xl/externalLinks/") for name in names):raise TransferError("IMPORT_XLSX_UNSAFE","Excel 宏或外部链接不允许导入")
        try:workbook=ET.fromstring(z.read("xl/workbook.xml"));rels=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        except (KeyError,ET.ParseError):raise TransferError("IMPORT_XLSX_INVALID","Excel 工作簿结构无效")
        relation_ns="{http://schemas.openxmlformats.org/package/2006/relationships}"
        targets={node.get("Id"):node.get("Target") for node in rels.findall(relation_ns+"Relationship")}
        sheets=[]
        for node in workbook.findall(".//"+NS+"sheet"):
            rid=node.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id");target=targets.get(rid,"")
            path="xl/"+target.lstrip("/").replace("../","")
            sheets.append((node.get("name"),path))
        if not sheets:raise TransferError("IMPORT_XLSX_INVALID","Excel 不包含工作表")
        selected=next((item for item in sheets if item[0]==sheet_name),None) if sheet_name else sheets[0]
        if not selected:raise TransferError("IMPORT_SHEET_NOT_FOUND","指定工作表不存在")
        shared=[]
        if "xl/sharedStrings.xml" in names:
            try:root=ET.fromstring(z.read("xl/sharedStrings.xml"));shared=["".join(n.text or "" for n in item.findall(".//"+NS+"t")) for item in root.findall(NS+"si")]
            except ET.ParseError:raise TransferError("IMPORT_XLSX_INVALID","共享字符串结构无效")
        try:root=ET.fromstring(z.read(selected[1]))
        except (KeyError,ET.ParseError):raise TransferError("IMPORT_XLSX_INVALID","工作表结构无效")
        rows=[]
        for row in root.findall(".//"+NS+"row"):
            values=[]
            for cell in row.findall(NS+"c"):
                ref=cell.get("r","");match=re.match(r"([A-Z]+)",ref)
                index=0
                if match:
                    for char in match.group(1):index=index*26+ord(char)-64
                    index-=1
                while len(values)<index:values.append("")
                values.append(_xlsx_cell(cell,shared))
            rows.append(values)
            if len(rows)>MAX_ROWS+1:break
        headers,data=_check_table(rows)
        return {"format":"xlsx","encoding":"OOXML","sheet":selected[0],"sheets":[item[0] for item in sheets],"headers":headers,"rows":data}

def parse_upload(filename,raw,sheet_name=None):
    if not raw:raise TransferError("IMPORT_EMPTY","文件为空")
    if len(raw)>MAX_FILE_BYTES:raise TransferError("IMPORT_FILE_TOO_LARGE","文件大小超过限制",{"max_bytes":MAX_FILE_BYTES})
    lower=filename.lower()
    if lower.endswith(".csv"):return parse_csv(raw)
    if lower.endswith(".xlsx"):return parse_xlsx(raw,sheet_name)
    raise TransferError("IMPORT_FORMAT_UNSUPPORTED","仅支持 .csv 和 .xlsx")

def infer_columns(headers,rows):
    result=[]
    for index,header in enumerate(headers):
        values=[row[index].strip() for row in rows if index<len(row) and row[index].strip()][:50]
        inferred="text"
        if values and all(re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)",v) for v in values):inferred="number"
        elif values and all(v.lower() in {"true","false","yes","no","1","0","是","否"} for v in values):inferred="checkbox"
        elif values and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}",v) for v in values):inferred="date"
        result.append({"header":header,"inferred_type":inferred,"samples":values[:3]})
    return result

def safe_cell(value):
    if value is None:return ""
    if isinstance(value,bool):text="true" if value else "false"
    elif isinstance(value,(dict,list)):text=str(value)
    else:text=str(value)
    probe=text.lstrip(" \t\r\n"+"".join(chr(index) for index in range(32)))
    return "'"+text if probe.startswith(("=","+","-","@")) else text

def make_csv(headers,rows):
    output=io.StringIO(newline="");writer=csv.writer(output,lineterminator="\r\n");writer.writerow([safe_cell(v) for v in headers]);writer.writerows([[safe_cell(v) for v in row] for row in rows])
    return ("\ufeff"+output.getvalue()).encode("utf-8")

def _xml_escape(value):
    return str(value).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def make_xlsx(headers,rows,sheet="Tasks"):
    all_rows=[headers,*rows];xml_rows=[]
    for r_index,row in enumerate(all_rows,1):
        cells=[]
        for c_index,value in enumerate(row,1):
            number=isinstance(value,(int,float)) and not isinstance(value,bool)
            col="";n=c_index
            while n:n,rem=divmod(n-1,26);col=chr(65+rem)+col
            if number:cells.append(f'<c r="{col}{r_index}"><v>{value}</v></c>')
            else:cells.append(f'<c r="{col}{r_index}" t="inlineStr"><is><t xml:space="preserve">{_xml_escape(safe_cell(value))}</t></is></c>')
        xml_rows.append(f'<row r="{r_index}">{"".join(cells)}</row>')
    worksheet='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+"".join(xml_rows)+"</sheetData></worksheet>"
    content='<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    workbook=f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{_xml_escape(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    wb_rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",content);z.writestr("_rels/.rels",rels);z.writestr("xl/workbook.xml",workbook);z.writestr("xl/_rels/workbook.xml.rels",wb_rels);z.writestr("xl/worksheets/sheet1.xml",worksheet)
    return output.getvalue()

import io
import unittest
import zipfile
from datetime import date
from xml.etree import ElementTree as ET

from flowboard.timeline_excel import TEMPLATE_ROWS, make_timeline_xlsx, make_timeline_template
from flowboard.transfer import XlsxNumericCell, make_xlsx, parse_upload


NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def parts(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class TimelineWorkbookTests(unittest.TestCase):
    def test_template_and_export_share_layout_and_editing_controls(self):
        template = parts(make_timeline_template())
        exported = parts(make_timeline_xlsx([
            ["项目A", "创意", "主线", "立项", "2026-10-01", "已完成", "备注"],
            ["项目B", "设计", "并行", "评审", "2026-10-02", "进行中", ""],
        ]))
        self.assertEqual(template["xl/styles.xml"], exported["xl/styles.xml"])
        self.assertEqual(template["xl/worksheets/sheet2.xml"], exported["xl/worksheets/sheet2.xml"])
        template_sheet = ET.fromstring(template["xl/worksheets/sheet1.xml"])
        export_sheet = ET.fromstring(exported["xl/worksheets/sheet1.xml"])
        for tag in ("cols", "sheetViews", "autoFilter", "dataValidations"):
            self.assertEqual(ET.tostring(template_sheet.find("s:" + tag, NS)), ET.tostring(export_sheet.find("s:" + tag, NS)))
        self.assertEqual(export_sheet.find(".//s:pane", NS).get("topLeftCell"), "A2")
        self.assertEqual(len(export_sheet.findall("s:cols/s:col", NS)), 7)
        validations = {n.get("sqref"): n for n in export_sheet.findall("s:dataValidations/s:dataValidation", NS)}
        for area, limit in (("A2:A1001", "200"), ("D2:D1001", "500"), ("G2:G1001", "500")):
            self.assertEqual(validations[area].find("s:formula1", NS).text, limit)
        self.assertEqual(validations["C2:C1001"].find("s:formula1", NS).text, '"主线,并行"')
        self.assertEqual(validations["F2:F1001"].find("s:formula1", NS).text, '"未开始,进行中,已完成"')
        self.assertEqual(validations["E2:E1001"].get("operator"), "between")
        formulas = [n.text for n in export_sheet.findall("s:conditionalFormatting/s:cfRule/s:formula", NS)]
        self.assertIn('$C2="并行"', formulas)
        self.assertIn('$F2="已完成"', formulas)

    def test_template_has_three_importable_examples_and_workflow_instructions(self):
        raw = make_timeline_template()
        parsed = parse_upload("template.xlsx", raw)
        self.assertEqual(parsed["sheets"], ["Timeline", "填写说明"])
        self.assertEqual(parsed["headers"], ["项目名称", "阶段", "主线/并行", "节点", "日期", "状态", "备注"])
        self.assertEqual(len(parsed["rows"]), 15)
        self.assertEqual(len({row[0] for row in parsed["rows"]}), 3)
        self.assertEqual({row[2] for row in parsed["rows"]}, {"主线", "并行"})
        self.assertEqual({row[1] for row in parsed["rows"]}, {"创意", "设计", "开发", "测试", "量产", "应用迭代"})
        for original, row in zip(TEMPLATE_ROWS, parsed["rows"]):
            self.assertEqual(row[:4], list(original[:4]))
            self.assertIsInstance(row[4], XlsxNumericCell)
            self.assertEqual(int(row[4]), (date.fromisoformat(original[4]) - date(1899, 12, 30)).days)
            self.assertEqual(row[5:], list(original[5:]))
        workbook = ET.fromstring(parts(raw)["xl/workbook.xml"])
        self.assertEqual(workbook.find('s:definedNames/s:definedName[@name="_xlnm.Print_Area"][@localSheetId="0"]', NS).text, 'Timeline!$A$1:$G$16')
        instructions = parts(raw)["xl/worksheets/sheet2.xml"].decode()
        for phrase in ("【单项目】", "【多项目】", "一次只导入所选 Sheet", "清除全部示例内容", "不能更新已有项目的节点"):
            self.assertIn(phrase, instructions)
        # Empty exports remain empty: examples are exclusive to the template.
        self.assertEqual(parse_upload('empty-export.xlsx', make_timeline_xlsx([]))['rows'], [])

    def test_export_native_dates_and_out_of_range_text_remain_importable(self):
        dates = ["1950-01-01", "2026-10-01", "2100-01-01", "1949-12-31", "2100-01-02"]
        raw = make_timeline_xlsx([["项目", "创意", "主线", str(index), value, "", ""] for index, value in enumerate(dates)])
        parsed = parse_upload("dates.xlsx", raw)
        for original, row in zip(dates, parsed["rows"]):
            if "1950-01-01" <= original <= "2100-01-01":
                self.assertIsInstance(row[4], XlsxNumericCell)
                self.assertEqual(int(row[4]), (date.fromisoformat(original) - date(1899, 12, 30)).days)
            else:
                self.assertNotIsInstance(row[4], XlsxNumericCell)
                self.assertEqual(row[4], original)
        styles = ET.fromstring(parts(raw)["xl/styles.xml"])
        self.assertEqual(styles.find("s:numFmts/s:numFmt", NS).get("formatCode"), "yyyy-mm-dd")

    def test_thousand_rows_and_long_text_fit_the_export_contract(self):
        raw = make_timeline_xlsx([[f"项目{index // 100}", "测试", "主线", str(index), "2026-10-01", "", "长备注" * 166] for index in range(1000)])
        self.assertEqual(len(parse_upload("large.xlsx", raw)["rows"]), 1000)
        sheet = ET.fromstring(parts(raw)["xl/worksheets/sheet1.xml"])
        self.assertEqual(sheet.find("s:autoFilter", NS).get("ref"), "A1:G1001")
        self.assertGreater(float(sheet.find('s:sheetData/s:row[@r="2"]', NS).get("ht")), 34)
        with self.assertRaises(ValueError):
            make_timeline_xlsx([[""] * 7] * 1001)

    def test_export_escapes_text_without_creating_cell_formulas(self):
        raw = make_timeline_xlsx([["=项目", "设计", "并行", "+节点", "2026-10-01", "", '@备注 <&> "测试"']])
        parsed = parse_upload("safe.xlsx", raw)
        self.assertEqual(parsed["rows"][0][0], "'=项目")
        self.assertEqual(parsed["rows"][0][3], "'+节点")
        self.assertEqual(parsed["rows"][0][6], '\'@备注 <&> "测试"')
        sheet = ET.fromstring(parts(raw)["xl/worksheets/sheet1.xml"])
        self.assertEqual(sheet.findall(".//s:c/s:f", NS), [])

    def test_legacy_board_export_stays_unchanged(self):
        raw = make_xlsx(["任务"], [["示例"]])
        self.assertEqual(parse_upload("board.xlsx", raw)["sheets"], ["Tasks"])
        self.assertNotIn("xl/styles.xml", parts(raw))


if __name__ == "__main__":
    unittest.main()

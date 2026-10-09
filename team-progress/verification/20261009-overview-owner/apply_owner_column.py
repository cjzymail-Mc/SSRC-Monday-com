from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'overview-ui.js';s=p.read_text(encoding='utf-8')
s=s.replace('colspan="6"','colspan="7"')
needle='</div></td><td class="ov-status ${kind}">${label}</td>'
assert needle in s
s=s.replace(needle,'</div></td><td class="ov-owner" title="${esc(p.creator_name)}" aria-label="${esc(p.creator_name)}">${esc(p.creator_name&&p.creator_name!==\'成员已不可用\'?Array.from(p.creator_name.trim())[0]||\'—\':\'—\')}</td><td class="ov-status ${kind}">${label}</td>')
s=s.replace('<col style="width:16%"><col style="width:105px">','<col style="width:16%"><col style="width:44px"><col style="width:105px">')
s=s.replace('<th>项目</th><th>关注状态</th>','<th>项目</th><th title="按项目创建者显示">负责人</th><th>关注状态</th>')
s=s.replace('节点备注对应主表显示的下一节点。','负责人沿用项目创建者关系，显示姓名首字，悬停可读完整姓名。节点备注对应主表显示的下一节点。')
p.write_text(s,encoding='utf-8')
p=ROOT/'overview.css';s=p.read_text(encoding='utf-8')+'\n.ov-project>td.ov-owner{text-align:center;padding:0 4px;color:#81758e;font-size:13px;white-space:nowrap}\n';p.write_text(s,encoding='utf-8')
p=ROOT/'index.html';s=p.read_text(encoding='utf-8').replace('20261009-f02-urgency-remarks','20261009-f02-owner-column');p.write_text(s,encoding='utf-8')
p=ROOT/'tests/overview_ui.test.js';s=p.read_text(encoding='utf-8').replace('colspan="6"','colspan="7"');p.write_text(s,encoding='utf-8')
p=ROOT/'tests/test_overview_ux_e2e.py';s=p.read_text(encoding='utf-8')
s=s.replace("['项目','关注状态','当前阶段','下一未完成节点','节点备注','项目进度']","['项目','负责人','关注状态','当前阶段','下一未完成节点','节点备注','项目进度']")
s=s.replace("self.assertEqual(risk.locator('td').count(),6)","self.assertEqual(risk.locator('td').count(),7)")
s=s.replace('querySelectorAll("col")[3].style.width','querySelectorAll("col")[4].style.width')
s=s.replace("self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),1244)","self.assertEqual(risk.locator('.ov-owner').inner_text(),'管')\n        self.assertEqual(risk.locator('.ov-owner').get_attribute('title'),'管理员')\n        self.assertEqual(risk.locator('.ov-owner').evaluate('el=>el.closest(\"table\").querySelector(\"col\").style.width'),'16%')\n        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),1244)")
p.write_text(s,encoding='utf-8')

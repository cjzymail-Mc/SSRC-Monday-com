from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'overview-ui.js';s=p.read_text(encoding='utf-8')
s=s.replace("function status(p){return p.overdue_count?['late',`逾期 ${p.overdue_count}`]:p.today_count?['today',`今日 ${p.today_count}`]", "function status(p){const overdue=p.total_overdue_count??p.overdue_count,today=p.total_today_count??p.today_count;return overdue?['late',`逾期 ${overdue}`]:today?['today',`今日 ${today}`]")
s=s.replace('colspan="5"','colspan="6"')
s=s.replace('</small>`:\'\'}</td><td><div class="ov-progress">','</small>`:\'\'}</td><td class="ov-main-remark"><span title="${esc(next?.remark||\'\')}">${esc(next?.remark||\'—\')}</span></td><td><div class="ov-progress">')
assert 'class="ov-main-remark"' in s
s=s.replace('<col style="width:28%"><col>','<col style="width:14%"><col><col style="width:110px">')
s=s.replace('<th>下一未完成节点</th><th>项目进度</th>','<th>下一未完成节点</th><th>节点备注</th><th>项目进度</th>')
s=s.replace('项目进度按项目全部有效节点计算。','项目按逾期、今日到期、未来节点排序；同类先看最早日期，同日按待处理数量排序。关注状态与分组取全项目风险，每个项目仅展示一次。节点备注对应主表显示的下一节点。项目进度按项目全部有效节点计算。')
p.write_text(s,encoding='utf-8')
p=ROOT/'overview.css';s=p.read_text(encoding='utf-8')+'\n.ov-main-remark>span{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;white-space:pre-line;overflow-wrap:anywhere;line-height:16px;font-size:12px;color:#81758e}\n';p.write_text(s,encoding='utf-8')
p=ROOT/'index.html';s=p.read_text(encoding='utf-8').replace('20261008-f02-detail-focus','20261009-f02-urgency-remarks');p.write_text(s,encoding='utf-8')
p=ROOT/'tests/test_overview_ux_e2e.py';s=p.read_text(encoding='utf-8').replace("['项目','关注状态','当前阶段','下一未完成节点','项目进度']","['项目','关注状态','当前阶段','下一未完成节点','节点备注','项目进度']");p.write_text(s,encoding='utf-8')

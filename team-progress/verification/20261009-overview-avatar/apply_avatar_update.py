from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'overview-ui.js';s=p.read_text(encoding='utf-8')
s=s.replace("next=p.next_nodes[0],progress=p.total_progress;", "next=p.next_nodes[0],progress=p.total_progress,avatarClass=['avatar-blue','avatar-pink','avatar-green','avatar-purple','avatar-orange'].includes(p.creator_avatar_class)?p.creator_avatar_class:'avatar-purple';")
old="${esc(p.creator_name&&p.creator_name!=='成员已不可用'?Array.from(p.creator_name.trim())[0]||'—':'—')}</td>"
assert old in s
s=s.replace(old,"<span class=\"ov-avatar ${avatarClass}\" aria-hidden=\"true\">${esc(p.creator_name&&p.creator_name!=='成员已不可用'?Array.from(p.creator_name.trim())[0]||'—':'—')}</span></td>")
s=s.replace('<col style="width:16%">','<col style="width:20.8%">')
s=s.replace('显示姓名首字，悬停可读完整姓名。','用圆形姓氏头像显示姓名首字，悬停可读完整姓名。')
p.write_text(s,encoding='utf-8')
p=ROOT/'overview.css';s=p.read_text(encoding='utf-8')+'\n.ov-avatar.avatar-blue{background:#6a8ed1}.ov-avatar.avatar-pink{background:#d77fa8}.ov-avatar.avatar-green{background:#5cae8d}.ov-avatar.avatar-purple{background:#806dcc}.ov-avatar.avatar-orange{background:#d99555}\n';p.write_text(s,encoding='utf-8')
p=ROOT/'index.html';s=p.read_text(encoding='utf-8').replace('20261009-f02-owner-column','20261009-f02-owner-avatar');p.write_text(s,encoding='utf-8')
p=ROOT/'tests/test_overview_ux_e2e.py';s=p.read_text(encoding='utf-8').replace("style.width'),'16%'","style.width'),'20.8%'")
needle="        self.assertEqual(risk.locator('.ov-owner').get_attribute('title'),'管理员')"
assert needle in s
s=s.replace(needle,needle+"\n        avatar=risk.locator('.ov-owner .ov-avatar')\n        self.assertEqual(avatar.inner_text(),'管')\n        self.assertEqual(avatar.evaluate('el=>getComputedStyle(el).borderRadius'),'50%')\n        self.assertEqual(avatar.evaluate('el=>getComputedStyle(el).width'),'27px')\n        self.assertEqual(avatar.evaluate('el=>getComputedStyle(el).height'),'27px')\n        self.assertNotIn(avatar.evaluate('el=>getComputedStyle(el).backgroundColor'),['transparent','rgba(0, 0, 0, 0)'])")
p.write_text(s,encoding='utf-8')
p=ROOT/'tests/overview_ui.test.js';s=p.read_text(encoding='utf-8').replace("assert.ok(!html.includes('onclick=\"bad'));", "assert.ok(!html.includes('onclick=\"bad'));assert.match(html,/class=\"ov-avatar avatar-purple\"/);")
p.write_text(s,encoding='utf-8')

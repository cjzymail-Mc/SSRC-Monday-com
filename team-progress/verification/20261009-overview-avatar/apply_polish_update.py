from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'overview-ui.js';s=p.read_text(encoding='utf-8')
s=s.replace("result.tag_id=tag;return result", "result.tag_id=tag;if(result.focus==='done'){result.focus='all';result.completion='done'}return result")
s=s.replace('payload=state.payload,counts=payload?.counts,tags=','payload=state.payload,tags=')
s=s.replace('<col><col style="width:110px">','<col><col style="width:16.3%">')
s=s.replace('<span class="ov-quick-label">节点</span>','')
s=s.replace('choices.focus.map(([value,text])=>','quickChoices.map(([value,text])=>')
s=s.replace('${f.focus===value}', '${quickSelected(f,value)}')
s=s.replace("${f.focus===value?'on':''}","${quickSelected(f,value)?'on':''}")
s=re.sub(r'<div class="ov-result" role="status">.*?</div><div class="ov-content">','<div class="ov-content">',s)
assert 'ov-result' not in s and 'ov-quick-label' not in s
p.write_text(s,encoding='utf-8')
p=ROOT/'overview.css';s=p.read_text(encoding='utf-8')
s=re.sub(r'\.ov-result[^{}]*\{[^}]*\}|\.ov-quick-label\{[^}]*\}','',s)
p.write_text(s,encoding='utf-8')
p=ROOT/'index.html';s=p.read_text(encoding='utf-8').replace('20261009-f02-owner-avatar','20261009-f02-overview-polish');p.write_text(s,encoding='utf-8')
p=ROOT/'tests/test_overview_ux_e2e.py';s=p.read_text(encoding='utf-8')
start=s.index('    def focus(self,page,key):')
end=s.index('\n    def test_menu_',start)
s=s[:start]+'''    def focus(self,page,key):
        parameter='completion=done' if key=='done' else f'period={key}' if key in ('week','month') else f'focus={key}'
        with page.expect_response(lambda r:'/timeline/overview?' in r.url and parameter in r.url and r.status==200) as response:
            if key=='done':self.select(page,'completion','done')
            else:page.locator(f'[data-overview-focus="{key}"]').click()
        self.ready(page)
        return response.value.json()
''' + s[end:]
s=s.replace("            self.focus(page,key)\n            self.assertIn(f'{projects} 个项目 · {nodes} 个节点',page.locator('.ov-result').inner_text())", "            payload=self.focus(page,key)\n            self.assertEqual((payload['counts']['projects'],payload['counts']['nodes']),(projects,nodes))\n            self.assertEqual(page.locator('.ov-project').count(),projects)")
s=s.replace("self.assertIn('创意',page.locator('.ov-result').inner_text());self.assertIn('主线',page.locator('.ov-result').inner_text())", "self.assertEqual(page.locator('[data-overview-filter=stage]').input_value(),'创意');self.assertEqual(page.locator('[data-overview-filter=track]').input_value(),'main')")
p.write_text(s,encoding='utf-8')
p=ROOT/'tests/test_overview_e2e.py';s=p.read_text(encoding='utf-8')
old="        pending[0].fulfill(response=response)\n        page.locator('.ov-result',has_text='1 个项目 · 1 个节点').wait_for()"
assert old in s
s=s.replace(old,"        with page.expect_response(lambda r:'/timeline/overview?' in r.url and parse_qs(urlparse(r.url).query).get('q')==['鞋面材料'] and r.status==200) as search_result:\n            pending[0].fulfill(response=response)\n        payload=search_result.value.json()\n        self.assertEqual((payload['counts']['projects'],payload['counts']['nodes']),(1,1))\n        page.locator('[data-timeline-page=overview][aria-busy=false]').wait_for()")
p.write_text(s,encoding='utf-8')

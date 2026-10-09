import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1000})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8083')
    page.locator('#loginUser').fill('test');page.locator('#loginPassword').fill('test')
    page.locator('#loginForm button[type=submit]').click()
    page.locator('[data-timeline-page="home"]').wait_for()
    page.locator('#timelineOverviewBtn').click()
    page.locator('.ov-project').first.wait_for()
    with page.expect_response(lambda r:'/timeline/overview?' in r.url and r.status==200):
        page.locator('[data-overview-filter="completion"]').select_option('all')
    page.locator('.ov-project').first.wait_for()
    page.wait_for_function('!document.querySelector("#toast").classList.contains("show")')
    assert page.locator('.ov-group-attention').count()==1
    assert page.locator('.ov-group-recent').count()==1
    page.screenshot(path=str(OUT/'preview-desktop.png'))
    page.locator('.ov-board').screenshot(path=str(OUT/'preview-content.png'))
    metrics=page.evaluate('''()=>{const css=s=>getComputedStyle(document.querySelector(s));return {viewport:[innerWidth,innerHeight],content:document.querySelector('.ov-board').getBoundingClientRect().toJSON(),heading_font:css('.ov-header h1').fontSize,tab_font:css('.ov-tabs button').fontSize,tab_underline:css('.ov-tabs .on').borderBottomColor,row_height:document.querySelector('.ov-project').getBoundingClientRect().height,row_font:css('.ov-open').fontSize,header_font:css('.ov-table th').fontSize,avatar:document.querySelector('.ov-avatar').getBoundingClientRect().toJSON(),group_purple:css('.ov-group-attention').getPropertyValue('--ov-group-color'),group_pink:css('.ov-group-recent').getPropertyValue('--ov-group-color'),status_fill:css('.ov-status.late').backgroundColor,progress_height:css('.ov-progress-track').height,result:document.querySelector('.ov-result').innerText}}''')
    assert metrics['row_height']==40
    assert metrics['heading_font']=='36px'
    assert metrics['row_font']=='14px'
    assert errors==[],errors
    (OUT/'visual-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    page.set_viewport_size({'width':760,'height':850})
    page.locator('.ov-table-scroll').first.evaluate('el=>el.scrollLeft=el.scrollWidth')
    page.screenshot(path=str(OUT/'preview-narrow.png'))
    browser.close()

from PIL import Image, ImageDraw
reference=Image.open(ROOT/'feature-02-进阶仪表盘/monday参考/7.png').convert('RGB').crop((65,241,1315,794))
reference.save(OUT/'reference-content-crop.png')
actual=Image.open(OUT/'preview-content.png').convert('RGB')
actual=actual.resize((1250,round(actual.height*1250/actual.width)))
actual=actual.crop((0,0,1250,553))
compare=Image.new('RGB',(2520,601),'#e9e6f0')
draw=ImageDraw.Draw(compare)
draw.text((18,14),'REFERENCE: 7.png content crop (1250 px)',fill='#282438')
draw.text((1278,14),'IMPLEMENTATION: live HTML/CSS, normalized to 1250 px',fill='#282438')
compare.paste(reference,(0,40));compare.paste(actual,(1270,40))
compare.save(OUT/'reference-comparison.png')
print('VISUAL_CAPTURE_PASS',json.dumps(metrics,ensure_ascii=False))

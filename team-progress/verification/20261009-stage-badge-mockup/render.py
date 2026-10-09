import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
target=ROOT/'feature-02-进阶仪表盘/（静态样张）当前阶段-圆角标签.html'
proof=[]
with sync_playwright() as runtime:
    browser=runtime.chromium.launch(headless=True)
    for width in [1480,794]:
        page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
        requests=[];errors=[]
        page.on('request',lambda request:requests.append(request.url))
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(target.as_uri())
        badges=page.locator('.ov-stage-badge').evaluate_all('els=>els.map(el=>({text:el.textContent,color:getComputedStyle(el).backgroundColor,radius:getComputedStyle(el).borderRadius,height:el.getBoundingClientRect().height,cell:getComputedStyle(el.parentElement).backgroundColor,cellWidth:el.parentElement.getBoundingClientRect().width,badgeWidth:el.getBoundingClientRect().width}))')
        assert len(badges)==9 and not errors
        assert not any(url.startswith('http') for url in requests),'standalone preview must not need remote resources'
        for badge in badges:
            assert badge['radius']=='6px' and badge['height']==26
            assert badge['cell']!=badge['color'] and badge['cellWidth']>badge['badgeWidth']
        assert {badge['text'] for badge in badges}=={'创意','设计','开发','测试','量产','应用迭代','未录入节点'}
        assert page.locator('.ov-project td.ov-status.late').first.evaluate('el=>getComputedStyle(el).backgroundColor')=='rgb(246, 51, 101)'
        page.screenshot(path=str(OUT/f'preview-{width}.png'),full_page=True)
        proof.append({'viewport_width':width,'badge_styles':badges,'no_remote_resources':True,'page_errors':errors})
        page.close()
    browser.close()
(OUT/'visual-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: standalone HTML at 1480 and 794 pixels; all six stages plus empty state; cell surface and status colors preserved.')

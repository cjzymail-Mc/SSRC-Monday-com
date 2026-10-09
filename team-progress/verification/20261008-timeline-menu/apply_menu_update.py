from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[3]
def edit(name, transform):
    p=ROOT/name
    old=p.read_text(encoding='utf-8')
    new=transform(old)
    assert old!=new,name
    p.write_text(new,encoding='utf-8')

def html(s):
    s=s.replace('title="时间画布"','title="项目时间轴"').replace('<span class="nav-label">时间画布</span>','<span class="nav-label">项目时间轴</span>')
    parent='id="timelineAllBtn"'
    start=s.index(parent)
    end=s.index('</button>',start)+len('</button>')
    s=s[:end]+'<div class="timeline-subnav" role="group" aria-label="项目时间轴范围"><button class="nav-item nav-button nav-child" id="timelineWeekBtn" title="本周" aria-pressed="false"><span class="nav-icon">⊢</span><span class="nav-label">本周</span></button><button class="nav-item nav-button nav-child" id="timelineMonthBtn" title="本月" aria-pressed="false"><span class="nav-icon">⌞</span><span class="nav-label">本月</span></button></div>'+s[end:]
    s=re.sub(r'<nav id="timelineCanvasNav".*?</nav>','',s)
    return s.replace('20261008-f02-ux-ready','20261008-f02-timeline-menu')
edit('index.html',html)

def app(s):
    s=s.replace("timelineCanvasScope='all';",'').replace(",timelineCanvasScope='all'",'')
    s=s.replace(',canvasScope:timelineCanvasScope','')
    s=s.replace("if(['all','week','month'].includes(saved?.canvasScope))timelineCanvasScope=saved.canvasScope;",'')
    s=s.replace("    if(timelinePortfolioModes.has(mode))timelineCanvasScope=mode;\n    else if(mode==='single')", "    if(mode==='single')")
    s=s.replace("const canvasNav=$('#timelineCanvasNav');if(canvasNav)canvasNav.hidden=!timelinePortfolioModes.has(mode);[['timelineCanvasAllBtn','all'],['timelineWeekBtn','week'],['timelineMonthBtn','month']]", "$('#timelineAllBtn')?.setAttribute('aria-current',navMode==='all'?'page':'false');[['timelineWeekBtn','week'],['timelineMonthBtn','month']]")
    s=s.replace("button.classList.toggle('on',mode===target);button.setAttribute('aria-pressed',String(mode===target))", "button.classList.toggle('active',navMode===target);button.setAttribute('aria-pressed',String(navMode===target))")
    s=s.replace("$('#timelineAllBtn').onclick=()=>openTimelineMode(timelineCanvasScope);$('#timelineCanvasAllBtn').onclick=()=>openTimelineMode('all');", "$('#timelineAllBtn').onclick=()=>openTimelineMode('all');")
    assert 'timelineCanvasScope' not in s
    assert 'timelineCanvasNav' not in s
    return s
edit('app.js',app)
edit('timeline-ui.js',lambda s:s.replace('返回时间画布','返回项目时间轴'))
edit('overview.css',lambda s:re.sub(r'\.ux-canvas-nav\{.*?\.ux-canvas-nav button\.on\{[^}]*\}', '', s).replace('.ux-canvas-nav{flex-wrap:wrap}','')+'\n.timeline-subnav .nav-item.active,.timeline-subnav .nav-item:hover,.timeline-subnav .nav-item:focus-visible{background:#ecebfa;color:#554ac7}.timeline-subnav .nav-item:focus-visible{outline:2px solid #9686dc;outline-offset:-2px}\n')

def ux(s):
    s=s.replace("'时间画布'","'项目时间轴'")
    s=s.replace("self.assertFalse(page.locator('#timelineCanvasNav').is_visible())", "self.assertEqual(page.locator('#timelineCanvasNav').count(),0)\n        self.assertEqual(page.locator('.timeline-subnav .nav-label').all_inner_texts(),['本周','本月'])")
    s=s.replace("page.locator('#timelineAllBtn').click();page.locator('#timelineCanvasNav').wait_for()", "page.locator('#timelineAllBtn').click();page.locator('[data-timeline-page=all]').wait_for()")
    s=s.replace("page.locator('#timelineAllBtn').click();page.locator('[data-timeline-page=month]').wait_for()\n        page.locator('#timelineCanvasAllBtn').click();page.locator('[data-timeline-page=all]').wait_for()", "page.locator('#timelineAllBtn').click();page.locator('[data-timeline-page=all]').wait_for()\n        self.assertEqual(page.locator('#timelineMonthBtn').get_attribute('aria-pressed'),'false')\n        self.assertEqual(page.locator('#timelineAllBtn').get_attribute('aria-current'),'page')\n        page.locator('#timelineWeekBtn').click();page.locator('[data-timeline-page=week]').wait_for()\n        page.locator('#timelineAllBtn').click();page.locator('[data-timeline-page=all]').wait_for()")
    return s
edit('tests/test_overview_ux_e2e.py',ux)
edit('tests/test_timeline_e2e.py',lambda s:s.replace("self.assertFalse(page.locator('#timelineCanvasNav').is_visible())", "self.assertEqual(page.locator('#timelineCanvasNav').count(),0)").replace("self.assertTrue(page.locator('#timelineCanvasNav').is_visible())", "self.assertTrue(page.locator('#timelineWeekBtn').is_visible())\n        self.assertTrue(page.locator('#timelineMonthBtn').is_visible())").replace('#timelineCanvasAllBtn','#timelineAllBtn'))

edit('README.md',lambda s:s.replace('本周/月位于「时间画布」内部','「项目时间轴」父菜单打开全部日期，本周/月位于其侧栏子菜单'))
edit('feature-02-进阶仪表盘/03-UX_OPTIMIZATION_CONTRACT.md',lambda s:s.replace('「时间画布」','「项目时间轴」').replace('本周/月是时间画布范围，不再作为独立侧栏模块。进入时间画布后显示全部日期/本周/本月三项范围切换','2026-10-08用户追加反馈：删除页面顶部整行范围导航；本周/月放到项目时间轴下面的侧栏子菜单，父菜单每次打开全部日期').replace('画布3范围','时间轴父菜单全部日期及本周/月子菜单'))
edit('feature-02-进阶仪表盘/04-UX_DELIVERY.md',lambda s:s.replace('「时间画布」切本周/本月，离开再回来保留范围','「项目时间轴」默认全部日期，侧栏子菜单切本周/本月；再次点击父菜单回到全部日期').replace('本周/月收进时间画布范围','本周/月作为项目时间轴的子菜单，父菜单打开全部日期').replace('画布范围和返回来源保留','当前页面刷新和下钻返回来源保留').replace('从其他模块进入本周/月画布首次需“时间画布→范围”两步，之后保留所选范围','本周/月由侧栏子菜单直接进入；点击“项目时间轴”始终打开全部日期').replace('只在按需', '只在按需')+'\n2026-10-08追加菜单反馈：统一名称为“项目时间轴”，顶部范围行删除，本周/月移入侧栏子菜单；最新验证见 `../team-progress/20261008-timeline-menu-feedback.md`。上方19项为UX初次收口证据，本次菜单增量另存证据，旧哈希清单仍绑定当时版本。\n')

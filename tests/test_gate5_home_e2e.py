"""Gate5 CP2 新增回归（只增不改删）：登录默认落「我的工作」主页 + 主页版式/入口。

依据 feature-01/11-GATE5_UX_REALIGNMENT_TASK.md §6/§12 与（Gate5静态稿·终稿）屏A。
独立 harness，不继承 test_timeline_e2e（避免父类用例被收集双跑）。
"""

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from flowboard.database import connect, migrate
from server import create_server


class Gate5HomeE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gate5-home-e2e-")
        self.db_path = str(Path(self.temp.name) / "flowboard.db")
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        migrate(self.db_path, initial_password="test-password")
        db = connect(self.db_path)
        db.execute("INSERT INTO users SELECT 'u2','u2','成员',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u2','member')")
        db.execute("INSERT INTO users SELECT 'u3','u3','只读',password_hash,NULL,NULL,1,'2026-01-01T00:00:00+00:00' FROM users WHERE id='u1'")
        db.execute("INSERT INTO workspace_memberships VALUES (1,'u3','viewer')")
        db.commit()
        db.close()
        self.server = create_server("127.0.0.1", 0, self.db_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()
        os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)

    def login(self, username):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.flowboard_console_errors = []
        page.flowboard_page_errors = []
        page.on("console", lambda message: page.flowboard_console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page.flowboard_page_errors.append(str(error)))
        page.goto(self.base)
        page.locator("#loginUser").fill(username)
        page.locator("#loginPassword").fill("test-password")
        page.locator("#loginForm button[type=submit]").click()
        page.locator("#currentUser > span:not(.avatar)").wait_for()
        page.locator("#loadState", has_text="刚刚同步").wait_for()
        page.wait_for_function("""() => {
            if (typeof state === 'undefined' || !state.current_user) return false;
            const canUseTimeline = Boolean(state.capabilities?.write || state.capabilities?.admin);
            return !canUseTimeline || Boolean(document.querySelector('[data-timeline-page="home"]'));
        }""")
        page.flowboard_console_errors.clear()
        page.flowboard_page_errors.clear()
        return context, page

    def assert_clean_browser(self, page):
        self.assertEqual(page.flowboard_page_errors, [])
        self.assertEqual(page.flowboard_console_errors, [])

    @staticmethod
    def physical_click(page, locator, button="left"):
        box = locator.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down(button=button)
        page.mouse.up(button=button)

    def seed_timeline(self, created_by="u1", name="落地项目"):
        db = connect(self.db_path)
        try:
            now = "2026-08-20T00:00:00+00:00"
            cur = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,?,1,?,?)", (name, created_by, now, now))
            project_id = cur.lastrowid
            for track, stage, node_name, date in (("main", "创意", "A1", "2026-08-01"), ("main", "设计", "A2", "2026-08-05"), ("parallel", "测试", "P1", "2026-08-03")):
                db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)", (project_id, track, stage, node_name, date, date, now, now))
            db.commit()
            return project_id
        finally:
            db.close()

    def seed_cp4_dashboard_projects(self):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        db = connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            projects = []
            fixtures = (
                ("CP4 重叠双轨", (("main", "创意", "主线一", today), ("main", "设计", "主线二", today), ("parallel", "测试", "并行一", today))),
                ("CP4 较早项目", (("main", "创意", "较早开始", today - timedelta(days=20)), ("main", "设计", "下一节点", today + timedelta(days=8)))),
            )
            for project_name, nodes in fixtures:
                cur = db.execute("INSERT INTO timeline_projects(workspace_id,name,created_by,version,created_at,updated_at) VALUES (1,?,'u1',1,?,?)", (project_name, now, now))
                project_id = cur.lastrowid
                projects.append(project_id)
                for track, stage, node_name, node_date in nodes:
                    value = node_date.isoformat()
                    db.execute("INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,remark,version,created_at,updated_at) VALUES (?,?,?,?,?,?,'',1,?,?)", (project_id, track, stage, node_name, value, value, now, now))
            db.commit()
            return projects, today.isoformat()
        finally:
            db.close()

    def test_gate5_default_lands_timeline_home_when_projects_exist(self):
        """有项目且可写：登录后默认落「我的工作」主页；经典看板区块隐藏但 #boardList 留在 DOM。"""
        self.seed_timeline(created_by="u1", name="落地项目")
        for index in range(25):
            self.seed_timeline(created_by="u1", name=f"一屏滚动项目 {index + 1:02d}")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(page.request.get(self.base + "/").headers.get("cache-control"), "no-store")
        self.assertEqual(page.locator('.timeline-shell>header, #timelineClose').count(), 0)
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assertFalse(page.locator(".breadcrumbs").is_visible())
        self.assertEqual(page.locator(".topbar").count(), 0)
        self.assertEqual(page.locator("#appSidebar > .sidebar-bottom .top-actions").count(), 1)
        self.assertLess(page.locator(".top-actions").bounding_box()["x"], 248)
        self.assertEqual(page.locator("#boardList").count(), 1)
        self.assertFalse(page.locator("#boardList").is_visible())
        self.assertEqual(page.locator("#dashboardBtn").count(), 0)
        self.assertEqual(page.locator(".workspace-switcher").count(), 0)
        self.assertEqual(page.locator(".main-nav > [data-sidebar-settings]").count(), 1)
        self.assertFalse(page.locator("#trashBtn").is_visible())
        self.assertEqual(page.locator("#appSidebar").evaluate("el => getComputedStyle(el).position"), "sticky")
        self.assertAlmostEqual(page.locator("#appSidebar").bounding_box()["height"], 800, delta=1)
        self.assertIn("落地项目", page.locator('[data-timeline-section="mine"]').inner_text())
        self.assertIn("我的项目", page.locator('[data-timeline-kpi="mine"]').inner_text())
        self.assert_clean_browser(page)
        # 即使旧 HTML 留下回退行，任一时间管理导航也必须主动清除它和空白占位。
        page.evaluate("""() => { const header=document.createElement('header'); header.innerHTML='<button id="timelineClose">←</button>'; document.querySelector('#timelineView>.timeline-shell').prepend(header) }""")
        self.assertEqual(page.locator('.timeline-shell>header, #timelineClose').count(), 2)
        self.assertFalse(page.locator('.timeline-shell>header').is_visible())
        self.physical_click(page, page.locator("#timelineAllBtn"))
        page.locator('[data-timeline-page="all"]').wait_for()
        self.assertEqual(page.locator('.timeline-shell>header, #timelineClose').count(), 0)
        viewport_metrics = page.evaluate("""() => ({
            viewport: innerHeight,
            pageHeight: document.documentElement.scrollHeight,
            canvasHeight: document.querySelector('[data-portfolio-scroll]').clientHeight,
            canvasScrollHeight: document.querySelector('[data-portfolio-scroll]').scrollHeight
        })""")
        self.assertLessEqual(viewport_metrics["pageHeight"], viewport_metrics["viewport"] + 1)
        self.assertGreater(viewport_metrics["canvasHeight"], 300)
        self.assertGreater(viewport_metrics["canvasScrollHeight"], viewport_metrics["canvasHeight"])
        for selector, mode in (("#timelineTagsBtn", "tags"), ("#archivedBtn", "archived"), ("#timelineBtn", "home")):
            page.evaluate("""() => { const header=document.createElement('header'); header.innerHTML='<button id="timelineClose">←</button>'; document.querySelector('#timelineView>.timeline-shell').prepend(header) }""")
            self.assertFalse(page.locator('.timeline-shell>header').is_visible())
            self.physical_click(page, page.locator(selector))
            page.locator(f'[data-timeline-page="{mode}"]').wait_for()
            self.assertEqual(page.locator('.timeline-shell>header, #timelineClose').count(), 0)
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assert_clean_browser(page); context.close()

    def test_home_feed_displays_audit_time_in_beijing_timezone(self):
        project_id = self.seed_timeline(created_by="u1", name="北京时间动态")
        stamp = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        expected = "今天 " + stamp.astimezone(timezone(timedelta(hours=8))).strftime("%H:%M")
        db = connect(self.db_path)
        try:
            node_id = db.execute(
                "SELECT id FROM timeline_nodes WHERE project_id=? ORDER BY id LIMIT 1",
                (project_id,),
            ).fetchone()["id"]
            batch_id = db.execute(
                """INSERT INTO timeline_change_batches(
                       project_id,actor_user_id,change_kind,trigger_source,
                       project_version_before,project_version_after,details_json,created_at
                   ) VALUES (?,'u1','direct_edit','editor',1,2,'{}',?)""",
                (project_id, stamp.isoformat()),
            ).lastrowid
            db.execute(
                """INSERT INTO timeline_node_changes(
                       batch_id,node_id,change_role,field,old_value,new_value
                   ) VALUES (?,?,'direct','remark','','北京时间测试')""",
                (batch_id, node_id),
            )
            db.commit()
        finally:
            db.close()
        context, page = self.login("u1")
        feed_time = page.locator('[data-timeline-feed="mine"] .tl-feed-item time').first
        feed_time.wait_for()
        self.assertEqual(feed_time.inner_text(), expected)
        self.assert_clean_browser(page)
        context.close()

    def test_sidebar_hover_treatment_is_shared_and_current_avatar_uses_name_initial(self):
        db = connect(self.db_path)
        try:
            db.execute("UPDATE users SET name='陈晶',avatar='林' WHERE id='u1'")
            db.commit()
        finally:
            db.close()
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(page.locator('#currentUser .avatar').inner_text(), '陈')
        self.assertEqual(page.locator('#currentUser > span:not(.avatar)').inner_text(), '陈晶')
        items = page.locator('.main-nav > .nav-item:visible')
        self.assertGreater(items.count(), 1)
        hover_styles = []
        for index in range(items.count()):
            item = items.nth(index)
            item.hover()
            hover_styles.append(item.evaluate("el => ({shadow:getComputedStyle(el).boxShadow,background:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color})"))
        self.assertTrue(all(style["shadow"] != "none" for style in hover_styles))
        self.assert_clean_browser(page); context.close()

    def test_gate5_default_lands_empty_timeline_without_projects(self):
        """无时间线项目也默认进入时间管理空态，经典主页保持隐藏。"""
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assertIn("暂无负责项目", page.locator('[data-timeline-section="mine"]').inner_text())
        self.assertEqual(page.locator('.tl-home-head input[name="name"]').count(), 0)
        self.physical_click(page, page.locator('[data-timeline-create-open]'))
        page.locator('#timelineModal [data-timeline-create]').wait_for()
        self.assertEqual(page.locator('#timelineModal input[name="name"]').get_attribute("maxlength"), "200")
        self.physical_click(page, page.locator('#timelineModal [data-timeline-create-cancel]').last)
        self.assertTrue(page.locator("#timelineModal").evaluate("element => element.hidden"))
        self.assert_clean_browser(page); context.close()

    def test_gate5_sidebar_collapses_to_icons_and_persists(self):
        """长项目页中按钮仍固定在视口中部；侧栏收起后仅留图标并记住偏好。"""
        for index in range(14):
            self.seed_timeline(created_by="u1", name=f"侧栏项目 {index + 1:02d}")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(page.locator("#timelineProjectNav").count(), 0)
        viewport_height = page.evaluate("window.innerHeight")
        self.assertEqual(page.locator("#sidebarToggle").evaluate("el => getComputedStyle(el).position"), "fixed")
        expanded_toggle_box = page.locator("#sidebarToggle").bounding_box()
        self.assertAlmostEqual(expanded_toggle_box["y"] + expanded_toggle_box["height"] / 2, viewport_height / 2, delta=2)
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        scrolled_toggle_box = page.locator("#sidebarToggle").bounding_box()
        self.assertAlmostEqual(scrolled_toggle_box["y"] + scrolled_toggle_box["height"] / 2, viewport_height / 2, delta=2)
        expanded_width = page.locator("#appSidebar").bounding_box()["width"]
        self.physical_click(page, page.locator("#sidebarToggle"))
        page.locator("#appSidebar.is-collapsed").wait_for()
        page.wait_for_timeout(360)
        sidebar_box = page.locator("#appSidebar").bounding_box()
        toggle_box = page.locator("#sidebarToggle").bounding_box()
        self.assertAlmostEqual(sidebar_box["width"], 64, delta=1)
        self.assertLess(sidebar_box["width"], expanded_width - 100)
        self.assertAlmostEqual(toggle_box["y"] + toggle_box["height"] / 2, viewport_height / 2, delta=2)
        self.assertAlmostEqual(toggle_box["x"] + toggle_box["width"] / 2, sidebar_box["x"] + sidebar_box["width"], delta=2)
        self.assertAlmostEqual(toggle_box["width"], 27, delta=1)
        self.assertAlmostEqual(toggle_box["height"], 58, delta=1)
        self.assertTrue(page.locator("#sidebarToggle").evaluate("""el => {
            const r=el.getBoundingClientRect(), points=[[r.left+6,r.top+r.height/2],[r.right-6,r.top+r.height/2],[r.left+r.width/2,r.top+6],[r.left+r.width/2,r.bottom-6]];
            return points.every(([x,y]) => document.elementFromPoint(x,y) === el);
        }"""), "the full visible collapse capsule must own pointer hit testing")
        self.assertGreater(float(page.locator("#sidebarToggle").evaluate("el => getComputedStyle(el).borderRadius").replace("px", "")), 20)
        self.assertFalse(page.locator("#timelineAllBtn .nav-label").is_visible())
        self.assertTrue(page.locator("#timelineAllBtn .nav-icon").is_visible())
        page.reload()
        page.locator("#appSidebar.is-collapsed").wait_for()
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assert_clean_browser(page); context.close()

    def test_gate5_home_kpi_tabs_feed_and_drilldown(self):
        """主页版式：KPI 四格 + 分区标签 + 成员长条药丸下钻 + 右栏动态随标签联动。"""
        (project_id, _), _today = self.seed_cp4_dashboard_projects()
        for index in range(9):
            self.seed_timeline(created_by="u1", name=f"折叠压力项目 {index + 1:02d}")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertEqual(page.locator("#breadcrumbBoard").inner_text(), "我的工作")
        self.assertEqual(page.locator('[data-timeline-page="home"] h1').inner_text(), "我的工作")
        self.assertEqual(page.locator('[data-timeline-mode="home"] > .timeline-toolbar').count(), 0)
        self.assertEqual(page.locator('[data-timeline-mode="home"] > .timeline-transfer').count(), 0)
        self.assertEqual(page.locator(".tl-home-head [data-timeline-import-open]").count(), 1)
        self.assertEqual(page.locator(".tl-home-head [data-timeline-import-file]").count(), 0)
        self.assertEqual(page.locator(".tl-home-head [data-timeline-export]").count(), 1)
        self.assertTrue(page.locator(".tl-home-head [data-timeline-create-open]").is_visible())
        self.assertEqual(page.locator('.tl-home-head input[name="name"]').count(), 0)
        self.assertEqual(page.locator("[data-timeline-kpi]").count(), 4)
        kpi_widths = page.locator("[data-timeline-kpi]").evaluate_all("nodes => nodes.map(node => node.getBoundingClientRect().width)")
        self.assertLessEqual(max(kpi_widths) - min(kpi_widths), 1)
        self.assertIn("我的项目（11）", page.locator('[data-timeline-tab="mine"]').inner_text())
        self.assertEqual(page.locator('[data-timeline-section="mine"] [data-project-choice]').count(), 11)
        self.assertIn("今日团队动态", page.locator('[data-timeline-kpi="feed"]').inner_text())
        feed_top = page.locator('.tl-feed').bounding_box()["y"]
        mine_border_top = page.locator('[data-timeline-section="mine"]').bounding_box()["y"]
        self.assertAlmostEqual(feed_top, mine_border_top, delta=1)
        # 切到团队项目：成员长条 + 每项目一枚药丸（全 DOM 唯一下钻钩子）
        page.locator('[data-timeline-tab="team"]').click()
        self.assertFalse(page.locator('[data-timeline-section="team"]').is_hidden())
        self.assertGreaterEqual(page.locator(".tl-mrow").count(), 2)
        pill = page.locator(f'[data-timeline-member-open="{project_id}"]')
        self.assertEqual(pill.count(), 1)
        member_toggle = page.locator('[data-timeline-member-toggle]')
        self.assertEqual(member_toggle.count(), 1)
        self.assertIn("显示全部（剩余 1 个）", member_toggle.inner_text())
        self.assertEqual(page.locator('[data-timeline-section="team"] [data-timeline-member-open]:visible').count(), 10)
        self.physical_click(page, member_toggle)
        self.assertEqual(page.locator('[data-timeline-section="team"] [data-timeline-member-open]:visible').count(), 11)
        self.assertEqual(member_toggle.inner_text(), "收起项目")
        self.physical_click(page, member_toggle)
        self.assertEqual(page.locator('[data-timeline-section="team"] [data-timeline-member-open]:visible').count(), 10)
        self.assertIn("团队 · 最近 20 条", page.locator("[data-timeline-feed-scope]").inner_text())
        self.assertTrue(page.locator('[data-timeline-feed="team"]').is_visible())
        # 药丸下钻 → 单项目仪表盘
        self.physical_click(page, pill)
        page.locator(f'[data-timeline-page="single"] [data-dashboard-project="{project_id}"]').wait_for()
        # KPI 下钻：团队类 KPI → 团队项目标签
        page.locator('[data-timeline-mode-target="home"]').click()
        page.locator('[data-timeline-page="home"]').wait_for()
        page.locator('[data-timeline-kpi="members"]').click()
        page.locator('[data-timeline-section="team"]').wait_for(state="visible")
        self.assertTrue(page.locator('[data-timeline-section="mine"]').is_hidden())
        self.assertFalse(page.locator('[data-timeline-section="team"]').is_hidden())
        self.assert_clean_browser(page); context.close()

    def test_gate5_single_dashboard_visual_alignment_and_real_drag(self):
        """屏B：节点/阶段条同轴、长文案不常驻；右键一次性解锁后真实拖动、放大带、草稿与提交闭环。"""
        project_id = self.seed_timeline(created_by="u1", name="拖拽手感项目")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="single"][data-project-id="{project_id}"]'))
        card = page.locator(f'[data-dashboard-project="{project_id}"]')
        card.wait_for()

        node = card.locator('.timeline-dashboard-node[data-node-date="2026-08-01"]')
        bar = card.locator('[data-stage-interval][data-stage="创意"]')
        node_box, bar_box = node.bounding_box(), bar.bounding_box()
        self.assertLessEqual(abs((node_box["y"] + node_box["height"] / 2) - (bar_box["y"] + bar_box["height"] / 2)), 1.5)
        source = node.locator(":scope > [data-node-tooltip-source]")
        tip = page.locator("[data-timeline-node-tooltip]")
        self.assertTrue(source.is_hidden(), "节点长名称源默认不得常驻挤压年度轴")
        self.assertTrue(tip.is_hidden(), "顶层节点提示框默认隐藏")
        self.assertIsNone(node.get_attribute("title"), "节点信息只保留自定义悬停卡，不再叠加浏览器原生 title")
        self.assertGreaterEqual(page.locator('[data-timeline-page="single"] .timeline-e-month').count(), 1)

        batch_requests = []
        page.on("request", lambda request: batch_requests.append(request) if request.method == "POST" and request.url.endswith("/timeline/batches") else None)
        node.hover()
        tip.wait_for(state="visible")
        tooltip_metrics = tip.evaluate("""el => {
          const r=el.getBoundingClientRect(), axis=document.querySelector('[data-timeline-page="single"] .timeline-portfolio-chart .timeline-e-axis')?.getBoundingClientRect(), label=el.getAttribute('data-placement');
          const overlaps=(a,b)=>Boolean(a&&b&&a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top);
          const previous=el.style.pointerEvents;el.style.pointerEvents='auto';
          const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);el.style.pointerEvents=previous;
          return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,viewportWidth:innerWidth,viewportHeight:innerHeight,topmost:hit===el||el.contains(hit),axisOverlap:overlaps(r,axis),placement:label,z:Number(getComputedStyle(el).zIndex)};
        }""")
        self.assertTrue(tooltip_metrics["topmost"], "节点提示框必须成为点击点处的最上层绘制元素")
        self.assertFalse(tooltip_metrics["axisOverlap"], "节点提示框不得遮挡固定年月日轴")
        self.assertGreaterEqual(tooltip_metrics["left"], 0)
        self.assertLessEqual(tooltip_metrics["right"], tooltip_metrics["viewportWidth"])
        self.assertGreaterEqual(tooltip_metrics["top"], 0)
        self.assertLessEqual(tooltip_metrics["bottom"], tooltip_metrics["viewportHeight"])
        self.assertIn(tooltip_metrics["placement"], {"left", "right", "above", "below"})
        self.physical_click(page, node, button="right")
        menu = page.locator('[data-timeline-page="single"] [data-timeline-context]')
        menu.wait_for(state="visible")
        tip.wait_for(state="hidden")
        self.assertTrue(menu.evaluate("""el => { const r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return hit===el||el.contains(hit) }"""), "右键菜单不得被今日线或过去蒙版覆盖")
        self.assertLess(int(menu.evaluate("el => getComputedStyle(el).zIndex")), tooltip_metrics["z"])
        self.assertTrue(node.evaluate("element => element.classList.contains('is-context-open')"))
        self.physical_click(page, menu.locator('[data-draft-action="single"]'))
        self.assertTrue(menu.is_hidden())
        self.assertFalse(node.evaluate("element => element.classList.contains('is-context-open')"))
        node = card.locator('.timeline-dashboard-node[data-node-date="2026-08-01"]')
        box = node.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 24, box["y"] + box["height"] / 2, steps=6)
        guides = page.locator('[data-timeline-page="single"] [data-portfolio-drag-guides]')
        self.assertFalse(guides.is_hidden())
        guide_label = guides.locator('.target-label')
        self.assertRegex(guide_label.inner_text(), r'^\d{4}-\d{2}-\d{2} \| [+-]?\d+天$')
        self.assertEqual(guide_label.locator('.target-delta').evaluate("el => getComputedStyle(el).color"), "rgb(255, 77, 90)")
        self.assertGreater(int(guides.evaluate("el => getComputedStyle(el).zIndex")), int(page.locator('[data-timeline-page="single"] .timeline-portfolio-today').evaluate("el => getComputedStyle(el).zIndex")))
        target_date = guide_label.inner_text().split(" | ", 1)[0]
        self.assertEqual(batch_requests, [], "拖动期间保持零网络")
        page.mouse.up()

        actions = page.locator('[data-single-dashboard-draft-actions]')
        actions.wait_for()
        self.assertEqual(actions.locator('button').all_inner_texts(), ['放弃', '更新 1'])
        self.assertEqual(actions.locator('[data-dashboard-undo]').count(), 0)
        scroll = page.locator('[data-timeline-page="single"] [data-portfolio-scroll]')
        axis = scroll.locator('.timeline-portfolio-axis-detail')
        for _ in range(8):
            if card.locator('.timeline-dashboard-node[data-node-id="1"]').count():
                break
            axis_box = axis.bounding_box()
            page.mouse.move(axis_box["x"] + axis_box["width"] * .35, axis_box["y"] + axis_box["height"] * .65)
            page.mouse.wheel(0, -120)
            page.wait_for_timeout(80)
        moved = card.locator('.timeline-dashboard-node[data-node-id="1"]').get_attribute("data-node-date")
        self.assertEqual(moved, target_date)
        self.assertEqual(card.locator(".timeline-dashboard-origin").count(), 1)
        self.assertEqual(batch_requests, [], "松手只落本地草稿")

        # 一次性解锁已消费：不重新右键时再次拖动不得改变草稿日期。
        node = card.locator('.timeline-dashboard-node[data-node-id="1"]')
        box = node.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down(); page.mouse.move(box["x"] + box["width"] / 2 + 70, box["y"] + box["height"] / 2); page.mouse.up()
        self.assertEqual(card.locator('.timeline-dashboard-node[data-node-id="1"]').get_attribute("data-node-date"), moved)

        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as saved:
            self.physical_click(page, actions.locator(f'[data-dashboard-submit="{project_id}"]'))
        self.assertEqual(saved.value.status, 200)
        actions.wait_for(state="detached")
        self.assertEqual(len(batch_requests), 1)
        undo_meta = card.locator('.timeline-portfolio-meta')
        self.physical_click(page, undo_meta, button="right")
        undo_menu = page.locator('[data-timeline-page="single"] [data-portfolio-undo-menu]')
        undo_menu.wait_for(state="visible")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches/undo")) as undone:
            self.physical_click(page, undo_menu.locator('[data-portfolio-undo-action]'))
        self.assertEqual(undone.value.status, 200)
        self.assertEqual(card.locator('.timeline-dashboard-node[data-node-id="1"]').get_attribute("data-node-date"), "2026-08-01")
        self.assert_clean_browser(page); context.close()

    def test_all_dashboard_project_menu_routes_back_and_uses_approved_hover_motion(self):
        project_id = self.seed_timeline(created_by="u1", name="返回路径项目")
        context, page = self.login("u1")
        self.physical_click(page, page.locator("#timelineAllBtn"))
        page.locator('[data-timeline-page="all"]').wait_for()

        meta = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-portfolio-meta')
        meta.wait_for()
        self.physical_click(page, meta, button="right")
        menu = page.locator('[data-timeline-page="all"] [data-portfolio-undo-menu]')
        menu.wait_for(state="visible")
        self.assertEqual(menu.locator('button').all_inner_texts(), ["在单仪表盘中查看", "撤销"])
        self.assertFalse(menu.locator('[data-portfolio-view-single]').is_disabled())
        self.assertTrue(menu.locator('[data-portfolio-undo-action]').is_disabled())

        # 仪表盘三类右键菜单全局互斥：项目 → 插入 → 项目 → 节点 → 项目。
        plot = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-stage-plot').first
        plot_box = plot.bounding_box()
        page.mouse.move(plot_box["x"] + plot_box["width"] * .92, plot_box["y"] + plot_box["height"] / 2)
        page.mouse.down(button="right"); page.mouse.up(button="right")
        insert_menu = page.locator('[data-timeline-page="all"] [data-dashboard-insert-menu]')
        insert_menu.wait_for(state="visible")
        self.assertTrue(menu.is_hidden())
        self.assertEqual(page.locator('[data-timeline-page="all"] [role="menu"]:visible').count(), 1)

        self.physical_click(page, meta, button="right")
        menu.wait_for(state="visible")
        self.assertTrue(insert_menu.is_hidden())
        node = page.locator(f'[data-dashboard-project="{project_id}"] .timeline-dashboard-node').first
        self.physical_click(page, node, button="right")
        node_menu = page.locator('[data-timeline-page="all"] [data-timeline-context]')
        node_menu.wait_for(state="visible")
        self.assertTrue(menu.is_hidden())
        self.assertEqual(page.locator('[data-timeline-page="all"] [role="menu"]:visible').count(), 1)

        self.physical_click(page, meta, button="right")
        menu.wait_for(state="visible")
        self.assertTrue(node_menu.is_hidden())
        self.assertEqual(page.locator('[data-timeline-page="all"] [role="menu"]:visible').count(), 1)

        self.physical_click(page, menu.locator('[data-portfolio-view-single]'))
        page.locator('[data-timeline-page="single"]').wait_for()
        back = page.locator('[data-timeline-mode-target="all"]')
        self.assertEqual(" ".join(back.inner_text().split()), "← 返回")
        back.hover()
        self.assertEqual(back.locator('.timeline-back-arrow').evaluate("el => getComputedStyle(el).animationName"), "timeline-back-arrow-spring")

        cancel_zoom = page.locator('[data-timeline-page="single"] [data-portfolio-cancel-zoom]')
        self.assertEqual(cancel_zoom.count(), 1)
        self.assertTrue(cancel_zoom.is_hidden())
        page.locator('[data-timeline-page="single"] [data-portfolio-zoom-in]').evaluate("el => el.click()")
        cancel_zoom.wait_for(state="visible")
        self.assertEqual(cancel_zoom.inner_text(), "取消缩放")
        self.assertEqual(cancel_zoom.evaluate("el => getComputedStyle(el).backgroundColor"), "rgb(229, 72, 77)")
        self.physical_click(page, cancel_zoom)
        page.wait_for_function("""() => {
            const card=document.querySelector('[data-timeline-page="single"]');
            const chart=card?.querySelector('.timeline-portfolio-chart');
            const button=card?.querySelector('[data-portfolio-cancel-zoom]');
            return chart && Number(chart.dataset.viewportDays) === Number(chart.dataset.fullDays) && button?.hidden;
        }""")

        self.physical_click(page, page.locator('[data-timeline-mode-target="editor"]'))
        page.locator('[data-timeline-page="editor"]').wait_for()
        self.assertEqual(" ".join(page.locator('[data-timeline-mode-target="all"]').inner_text().split()), "← 返回")
        self.physical_click(page, page.locator('[data-timeline-mode-target="all"]'))
        page.locator('[data-timeline-page="all"]').wait_for()

        self.physical_click(page, page.locator("#timelineBtn"))
        page.locator('[data-timeline-page="home"]').wait_for()
        self.physical_click(page, page.locator(f'[data-timeline-open="single"][data-project-id="{project_id}"]'))
        page.locator('[data-timeline-page="single"]').wait_for()
        home_back = page.locator('[data-timeline-mode-target="home"]')
        self.assertEqual(" ".join(home_back.inner_text().split()), "← 我的工作")
        home_back.hover()
        self.assertEqual(home_back.locator('.timeline-back-arrow').evaluate("el => getComputedStyle(el).animationName"), "timeline-back-arrow-spring")
        self.assert_clean_browser(page); context.close()

    def test_drag_modes_persist_only_the_intended_dates_and_audit_roles(self):
        """真实拖拽提交：single 只改当前节点；cascade 由服务端生成 cascaded 行。"""
        single_project = self.seed_timeline(created_by="u1", name="仅当前节点项目")
        cascade_project = self.seed_timeline(created_by="u1", name="顺延审计项目")
        context, page = self.login("u1")

        def project_snapshot(project_id):
            db = connect(self.db_path)
            try:
                return [dict(row) for row in db.execute(
                    "SELECT id,name,date FROM timeline_nodes WHERE project_id=? AND track='main' ORDER BY date,name,id",
                    (project_id,),
                )]
            finally:
                db.close()

        def drag_first_node(project_id, action):
            self.physical_click(page, page.locator(f'[data-timeline-open="single"][data-project-id="{project_id}"]'))
            card = page.locator(f'[data-dashboard-project="{project_id}"]')
            card.wait_for()
            first_id = project_snapshot(project_id)[0]["id"]
            node = card.locator(f'.timeline-dashboard-node[data-node-id="{first_id}"]')
            self.physical_click(page, node, button="right")
            menu = page.locator('[data-timeline-page="single"] [data-timeline-context]')
            menu.wait_for(state="visible")
            self.physical_click(page, menu.locator(f'[data-draft-action="{action}"]'))
            box = node.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 24, box["y"] + box["height"] / 2, steps=6)
            page.mouse.up()
            actions = page.locator('[data-single-dashboard-draft-actions]')
            actions.wait_for()
            self.assertEqual(actions.locator('[data-dashboard-submit]').inner_text(), "更新 1")
            with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as saved:
                self.physical_click(page, actions.locator('[data-dashboard-submit]'))
            self.assertEqual(saved.value.status, 200)
            actions.wait_for(state="detached")

        single_before = project_snapshot(single_project)
        drag_first_node(single_project, "single")
        single_after = project_snapshot(single_project)
        self.assertNotEqual(single_after[0]["date"], single_before[0]["date"])
        self.assertEqual(single_after[1]["date"], single_before[1]["date"])

        self.physical_click(page, page.locator('[data-timeline-mode-target="home"]'))
        page.locator('[data-timeline-page="home"]').wait_for()
        cascade_before = project_snapshot(cascade_project)
        drag_first_node(cascade_project, "cascade")
        cascade_after = project_snapshot(cascade_project)
        first_delta = (datetime.fromisoformat(cascade_after[0]["date"]) - datetime.fromisoformat(cascade_before[0]["date"])).days
        second_delta = (datetime.fromisoformat(cascade_after[1]["date"]) - datetime.fromisoformat(cascade_before[1]["date"])).days
        self.assertNotEqual(first_delta, 0)
        self.assertEqual(second_delta, first_delta)

        db = connect(self.db_path)
        try:
            batches = db.execute(
                "SELECT id,project_id,details_json FROM timeline_change_batches WHERE project_id IN (?,?) ORDER BY id",
                (single_project, cascade_project),
            ).fetchall()
            self.assertEqual([json.loads(row["details_json"])["mode"] for row in batches], ["single", "cascade"])
            single_rows = [tuple(row) for row in db.execute(
                "SELECT c.node_id,c.change_role,c.field FROM timeline_node_changes c WHERE c.batch_id=? ORDER BY c.id",
                (batches[0]["id"],),
            )]
            cascade_rows = [tuple(row) for row in db.execute(
                "SELECT c.node_id,c.change_role,c.field FROM timeline_node_changes c WHERE c.batch_id=? ORDER BY c.id",
                (batches[1]["id"],),
            )]
            self.assertEqual(single_rows, [(single_before[0]["id"], "direct", "date")])
            self.assertEqual(cascade_rows, [
                (cascade_before[0]["id"], "direct", "date"),
                (cascade_before[1]["id"], "cascaded", "date"),
            ])
        finally:
            db.close()
        self.assert_clean_browser(page)
        context.close()

    def test_all_dashboard_dense_cluster_single_drag_uses_one_day_collision_push(self):
        """全局视图保持原缩放/聚合，但拥挤簇可代理最早节点并按 1 天碰撞顺延。"""
        project_id = self.seed_timeline(created_by="u1", name="一日最小间隔项目")
        range_project_id = self.seed_timeline(created_by="u1", name="全局范围项目")
        db = connect(self.db_path)
        try:
            main_nodes = db.execute(
                "SELECT id,name,date FROM timeline_nodes WHERE project_id=? AND track='main' ORDER BY date,id",
                (project_id,),
            ).fetchall()
            first_id, second_id = main_nodes[0]["id"], main_nodes[1]["id"]
            db.execute("UPDATE timeline_nodes SET date='2026-08-08',initial_date='2026-08-08' WHERE id=?", (second_id,))
            range_nodes = db.execute(
                "SELECT id FROM timeline_nodes WHERE project_id=? AND track='main' ORDER BY date,id",
                (range_project_id,),
            ).fetchall()
            db.execute("UPDATE timeline_nodes SET date='2025-01-01',initial_date='2025-01-01' WHERE id=?", (range_nodes[0]["id"],))
            db.execute("UPDATE timeline_nodes SET date='2027-12-31',initial_date='2027-12-31' WHERE id=?", (range_nodes[1]["id"],))
            db.commit()
        finally:
            db.close()

        context, page = self.login("u1")
        self.physical_click(page, page.locator("#timelineAllBtn"))
        all_page = page.locator('[data-timeline-page="all"]')
        all_page.wait_for()
        chart = all_page.locator(".timeline-portfolio-chart")
        self.assertEqual(chart.get_attribute("data-viewport-days"), chart.get_attribute("data-full-days"))
        card = all_page.locator(f'[data-dashboard-project="{project_id}"]')
        cluster = card.locator(
            f'.timeline-node-cluster[data-cluster-drag-proxy="earliest"][data-node-id="{first_id}"]'
        )
        cluster.wait_for()
        self.assertEqual(card.locator('[data-stage-interval][data-stage="测试"]').count(), 0)

        self.physical_click(page, cluster, button="right")
        menu = all_page.locator("[data-timeline-context]")
        menu.wait_for(state="visible")
        self.assertEqual(
            menu.locator('[data-draft-action="single"], [data-draft-action="cascade"]').all_inner_texts(),
            ["拖拽（仅当前节点）", "拖拽（顺延）"],
        )
        self.physical_click(page, menu.locator('[data-draft-action="single"]'))
        box = cluster.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 24, box["y"] + box["height"] / 2, steps=6)
        page.mouse.up()
        submit = card.locator(f'[data-dashboard-submit="{project_id}"]')
        submit.wait_for()
        self.assertEqual(submit.inner_text(), "更新 1")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/timeline/batches")) as saved:
            self.physical_click(page, submit)
        self.assertEqual(saved.value.status, 200)

        db = connect(self.db_path)
        try:
            after = db.execute(
                "SELECT id,date FROM timeline_nodes WHERE id IN (?,?) ORDER BY date,id",
                (first_id, second_id),
            ).fetchall()
            self.assertEqual([row["id"] for row in after], [first_id, second_id])
            first_date = datetime.fromisoformat(after[0]["date"])
            second_date = datetime.fromisoformat(after[1]["date"])
            self.assertGreater(first_date, datetime.fromisoformat("2026-08-01"))
            self.assertEqual((second_date - first_date).days, 1)
            batch = db.execute(
                "SELECT id,details_json FROM timeline_change_batches WHERE project_id=? ORDER BY id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            self.assertEqual(json.loads(batch["details_json"])["mode"], "single")
            rows = [tuple(row) for row in db.execute(
                "SELECT node_id,change_role,field FROM timeline_node_changes WHERE batch_id=? ORDER BY id",
                (batch["id"],),
            )]
            self.assertEqual(rows, [(first_id, "direct", "date"), (second_id, "cascaded", "date")])
        finally:
            db.close()
        self.assert_clean_browser(page)
        context.close()

    def test_gate5_viewer_never_sees_classic_home_without_probe_noise(self):
        """只读成员不自动探测时间轴，经典主页仍保持彻底隐藏。"""
        self.seed_timeline(created_by="u1", name="只读可见项目")
        context, page = self.login("u3")
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assert_clean_browser(page)
        self.assertTrue(page.locator("#timelineModal").evaluate("element => element.hidden"))
        with page.expect_response(lambda response: response.url.endswith("/api/workspaces/1/timeline")) as denied:
            self.physical_click(page, page.locator("#timelineBtn"))
        page.locator("#toast.show").wait_for()
        self.assertFalse(page.locator("#timelineView").is_visible())
        self.assertEqual(denied.value.status, 403)
        self.assertEqual(len(page.flowboard_console_errors), 1)
        self.assertIn("403", page.flowboard_console_errors[0])
        context.close()

    def test_gate5_delete_last_project_leaves_home_stable(self):
        """删掉最后一个项目后主页稳定呈现空态，无 JS 错误。"""
        self.seed_timeline(created_by="u1", name="最后项目")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        page.once("dialog", lambda dialog: dialog.accept())
        self.physical_click(page, page.locator("[data-timeline-delete]"))
        page.locator("[data-project-choice]").wait_for(state="detached")
        self.assertEqual(page.locator("[data-project-choice]").count(), 0)
        self.assertIn("暂无负责项目", page.locator('[data-timeline-section="mine"]').inner_text())
        self.assert_clean_browser(page); context.close()

    def test_gate5_url_board_param_cannot_restore_classic_home(self):
        """旧 ?board= 恢复参数不得重新暴露经典主页。"""
        self.seed_timeline(created_by="u1", name="恢复项目")
        context, page = self.login("u1")
        page.locator('[data-timeline-page="home"]').wait_for()
        page.goto(f"{self.base}/?board=1")
        page.locator('[data-timeline-page="home"]').wait_for()
        self.assertFalse(page.locator("#boardWorkspace").is_visible())
        self.assert_clean_browser(page); context.close()


if __name__ == "__main__":
    unittest.main()

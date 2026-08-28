import os
import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from server import create_server
from test_secure_foundation import create_legacy_database, make_two_sheet_xlsx


class FlowboardViewsE2E(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flowboard-e2e-")
        self.db_path = str(Path(self.temp.name) / "flowboard.db")
        create_legacy_database(self.db_path)
        os.environ["FLOWBOARD_INITIAL_PASSWORD"] = "test-password"
        self.server = create_server("127.0.0.1", 0, self.db_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start(); self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)

    def tearDown(self):
        self.browser.close(); self.playwright.stop()
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.temp.cleanup(); os.environ.pop("FLOWBOARD_INITIAL_PASSWORD", None)

    def login_page(self, username="u1", viewport=None):
        context = self.browser.new_context(viewport=viewport or {"width": 1280, "height": 800})
        page = context.new_page(); page.goto(self.base)
        page.locator("#loginUser").fill(username); page.locator("#loginPassword").fill("test-password")
        page.locator("#loginForm button[type=submit]").click()
        page.locator(".task-row").first.wait_for()
        return context, page

    def test_real_app_tabs_saved_resize_drag_calendar_viewer_and_mobile(self):
        context, page = self.login_page()
        initial_titles = page.locator(".task-name").all_text_contents()
        page.locator('[data-view-type="kanban"]').click(); page.locator(".kanban-column").first.wait_for()
        self.assertEqual(sorted(page.locator(".view-card").all_text_contents()), sorted(initial_titles))
        source = page.locator(".view-card").first
        move_responses = []
        def capture(response):
            if "/kanban-move" in response.url: move_responses.append({"request": response.request.post_data, "response": response.json()})
        page.on("response", capture)
        source_title = source.text_content(); target = None
        for index in range(page.locator(".kanban-column").count()):
            column = page.locator(".kanban-column").nth(index)
            if column.locator(".view-card", has_text=source_title).count() == 0:
                target = column.locator(".card-drop.tail"); break
        self.assertIsNotNone(target); source.drag_to(target); page.wait_for_timeout(700)
        self.assertEqual(page.locator("#toast").text_content(), "Kanban 顺序已保存", move_responses)
        source = page.locator(".view-card", has_text=source_title).first; source_id = source.get_attribute("data-view-task")
        lane = source.locator("xpath=ancestor::section[contains(@class,'kanban-column')]")
        same_lane_target = None
        for index in range(lane.locator(".card-drop:not(.tail)").count()):
            candidate = lane.locator(".card-drop:not(.tail)").nth(index)
            if candidate.get_attribute("data-anchor-task") != source_id: same_lane_target = candidate; break
        if same_lane_target is not None:
            source.drag_to(same_lane_target); page.wait_for_timeout(700)
            self.assertGreaterEqual(len(move_responses), 2, move_responses)
        order_before_reload = page.locator(".view-card").all_text_contents()
        page.reload(); page.locator(".task-row").first.wait_for()
        page.locator('[data-view-type="kanban"]').click(); page.locator(".kanban-column").first.wait_for()
        self.assertEqual(page.locator(".view-card").all_text_contents(), order_before_reload)
        page.locator('[data-view-type="calendar"]').click(); page.locator(".calendar-grid").wait_for()
        self.assertEqual(page.locator(".calendar-day").count(), 42)
        undated = page.locator(".undated .view-card").first
        if undated.count():
            title = undated.text_content(); undated.dispatch_event("dragstart"); page.locator(".calendar-day:not(.outside)").first.dispatch_event("drop")
            page.wait_for_timeout(500)
            page.locator(".calendar-grid").wait_for(); self.assertTrue(page.locator(".calendar-day .view-card", has_text=title).count())
        page.locator('[data-view-type="table"]').click(); page.locator(".task-row").first.wait_for()
        answers = iter(["create", "E2E 表格", "personal", "table", None, "{}", ""]); seen_dialogs = []; page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        def answer(dialog):
            seen_dialogs.append((dialog.message, dialog.default_value))
            value = next(answers); dialog.accept(dialog.default_value if value is None else value)
        page.on("dialog", answer)
        self.assertEqual(page.locator("#viewBtn").evaluate("el => typeof el.onclick"), "function")
        page.evaluate("manageViewsProduction()")
        page.wait_for_timeout(800)
        self.assertEqual(page.locator("#toast").text_content(), "视图操作完成", {"dialogs": seen_dialogs, "errors": page_errors})
        handle = page.locator('[data-resize="title"]').first; box = handle.bounding_box(); self.assertIsNotNone(box)
        page.mouse.move(box["x"] + 2, box["y"] + 5); page.mouse.down(); page.mouse.move(box["x"] + 62, box["y"] + 5); page.mouse.up()
        page.wait_for_timeout(400); before = page.locator(".dynamic-grid").first.get_attribute("style")
        page.reload(); page.locator(".dynamic-grid").first.wait_for(); after = page.locator(".dynamic-grid").first.get_attribute("style")
        self.assertEqual(before, after)
        role_status = page.evaluate("""async () => {
          const session = await (await fetch('/api/session')).json();
          const response = await fetch('/api/admin/workspace-memberships/u2?workspace_id=1', {
            method:'PATCH', headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},
            body:JSON.stringify({role:'viewer'})}); return response.status;
        }""")
        self.assertEqual(role_status, 200)
        viewer_context, viewer = self.login_page("u2")
        viewer.locator('[data-view-type="kanban"]').click(); viewer.locator(".view-card").first.wait_for()
        self.assertEqual(viewer.locator('.view-card[draggable="true"]').count(), 0)
        mobile_context, mobile = self.login_page(viewport={"width": 390, "height": 844})
        mobile.locator('[data-view-type="kanban"]').click(); mobile.locator(".kanban").wait_for()
        self.assertGreater(mobile.locator(".kanban").evaluate("el => el.scrollWidth"), 390)
        mobile.locator('[data-view-type="calendar"]').click(); mobile.locator(".calendar-grid").wait_for()
        self.assertGreaterEqual(mobile.locator(".calendar-grid").evaluate("el => el.scrollWidth"), 770)
        mobile_context.close(); viewer_context.close(); context.close()

    def test_real_app_template_import_and_export(self):
        context,page=self.login_page(viewport={"width":390,"height":844})
        page.locator("#templateBtn").click();page.locator("#saveTemplateBtn").wait_for()
        page.locator("#templateName").fill("E2E 项目模板");page.locator("#templateType").select_option("project");page.locator("#saveTemplateBtn").click();page.locator("[data-edit-template]").first.wait_for();self.assertIn("项目模板",page.locator(".transfer-card").first.text_content())
        page.once("dialog",lambda dialog:dialog.accept("E2E 已更新项目模板"));page.locator("[data-edit-template]").first.click();page.locator(".transfer-card",has_text="E2E 已更新项目模板").wait_for()
        page.once("dialog",lambda dialog:dialog.accept());page.locator("[data-delete-template]").first.click();page.locator("#toggleDeletedTemplates").click();page.locator("[data-restore-template]").first.wait_for();self.assertIn("已删除",page.locator(".transfer-card").first.text_content());page.locator("[data-restore-template]").first.click();page.locator("[data-use-template]").first.wait_for()
        page.once("dialog",lambda dialog:dialog.accept("E2E 项目实例"));page.locator("[data-use-template]").first.click();page.locator("#boardTitle",has_text="E2E 项目实例").wait_for()
        workbook=make_two_sheet_xlsx(["Title"],[["ignore-first-sheet"]],["Title"],[["E2E XLSX second sheet"]]);page.locator("#importBtn").click();page.locator("#importFile").set_input_files({"name":"e2e-multi.xlsx","mimeType":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","buffer":workbook});page.locator("#previewImportBtn").click();page.locator("#importSheet").wait_for();self.assertEqual(page.locator("#importSheet").input_value(),"First");page.locator("#importSheet").select_option("Second");page.locator("#importPreview",has_text="E2E XLSX second sheet").wait_for();self.assertIn("推断 text",page.locator(".mapping-row small").first.text_content());page.locator("#commitImportBtn").click();page.locator(".task-name",has_text="E2E XLSX second sheet").wait_for()
        page.once("dialog",lambda dialog:dialog.accept("csv"))
        with page.expect_download() as download_info:page.locator("#exportBtn").click()
        download=download_info.value;self.assertTrue(download.suggested_filename.endswith(".csv"));self.assertEqual(page.locator("#toast").text_content().startswith("已导出"),True)
        context.close()

    def test_real_app_hierarchy_dependency_cycle_progress_and_date_policy(self):
        context, page = self.login_page()
        rows = page.locator(".task-row"); self.assertGreaterEqual(rows.count(), 2)
        parent_id = int(rows.nth(0).get_attribute("data-task")); predecessor_id = int(rows.nth(1).get_attribute("data-task"))
        rows.nth(0).click(); page.locator("#addSubtaskBtn").wait_for()
        page.once("dialog", lambda dialog: dialog.accept("E2E 子任务一")); page.locator("#addSubtaskBtn").click(); page.get_by_text("E2E 子任务一 · 待开始", exact=True).wait_for()
        page.once("dialog", lambda dialog: dialog.accept("E2E 子任务二")); page.locator("#addSubtaskBtn").click(); page.get_by_text("E2E 子任务二 · 待开始", exact=True).wait_for()
        child_rows = page.locator("[data-child-move]"); self.assertEqual(child_rows.count(), 4); child_id=int(child_rows.nth(0).get_attribute("data-child-move"))
        child_rows.nth(1).click(); page.wait_for_timeout(400)
        page.locator('[data-close="taskModal"]').evaluate("el => el.click()")
        date_status = page.evaluate(f"""async () => {{
          const session=await (await fetch('/api/session')).json(); const headers={{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token}};
          for (const [id,due] of [[{parent_id},'2026-08-10'],[{predecessor_id},'2026-08-20']]) {{
            const task=await (await fetch('/api/tasks/'+id)).json(); const response=await fetch('/api/tasks/'+id,{{method:'PATCH',headers,body:JSON.stringify({{version:task.version,due}})}}); if(!response.ok)return response.status;
          }} return 200;
        }}"""); self.assertEqual(date_status, 200)
        page.reload(); page.locator(f'[data-task="{parent_id}"]').click(); page.locator("#addDependencyBtn").wait_for()
        answers = iter([str(predecessor_id), True])
        def dependency_dialog(dialog):
            value=next(answers); dialog.accept(value if isinstance(value,str) else None)
        page.on("dialog",dependency_dialog); page.locator("#addDependencyBtn").click(); page.get_by_text("阻塞中").wait_for(); page.remove_listener("dialog",dependency_dialog)
        self.assertEqual(page.locator('[data-field="due"]').input_value(),"2026-08-20")
        page.locator('[data-close="taskModal"]').evaluate("el => el.click()"); page.locator('[data-view-type="kanban"]').click()
        parent_card=page.locator(f'[data-view-task="{parent_id}"]'); self.assertIn("阻塞",parent_card.text_content())
        page.locator('[data-view-type="calendar"]').click(); parent_card=page.locator(f'[data-view-task="{parent_id}"]'); self.assertIn("阻塞",parent_card.text_content())
        page.locator('[data-view-type="table"]').click(); page.locator(f'[data-task="{predecessor_id}"]').click(); page.locator("#addDependencyBtn").wait_for()
        cycle_answers=iter([str(parent_id),False])
        def cycle_dialog(dialog):
            value=next(cycle_answers); dialog.accept(value) if isinstance(value,str) else dialog.dismiss()
        page.on("dialog",cycle_dialog);page.locator("#addDependencyBtn").click();page.get_by_text("依赖会形成循环").wait_for();page.remove_listener("dialog",cycle_dialog)
        complete_status=page.evaluate(f"""async () => {{const s=await (await fetch('/api/session')).json();const t=await (await fetch('/api/tasks/{predecessor_id}')).json();return (await fetch('/api/tasks/{predecessor_id}',{{method:'PATCH',headers:{{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}},body:JSON.stringify({{version:t.version,status:'已完成'}})}})).status}}""")
        self.assertEqual(complete_status,200);page.locator('[data-close="taskModal"]').evaluate("el => el.click()");page.reload();page.locator(f'[data-task="{parent_id}"]').click();page.get_by_text("当前不阻塞").wait_for();self.assertIn("2",page.locator(".relation-section").first.text_content())
        page.locator('[data-close="taskModal"]').evaluate("el => el.click()")
        stale_snapshot=page.evaluate(f"""async()=>{{const t=await(await fetch('/api/tasks/{child_id}')).json();const b=await(await fetch('/api/bootstrap')).json();return{{version:t.version,board_version:b.board.version}}}}""")
        other_context, other_page=self.login_page(); mutate_status=other_page.evaluate(f"""async()=>{{const s=await(await fetch('/api/session')).json();return(await fetch('/api/tasks/{child_id}/parent',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}},body:JSON.stringify({{version:{stale_snapshot['version']},board_version:{stale_snapshot['board_version']},parent_id:{parent_id},position:0}})}})).status}}""");self.assertEqual(mutate_status,200)
        stale_status=page.evaluate(f"""async()=>{{const s=await(await fetch('/api/session')).json();return(await fetch('/api/tasks/{child_id}/parent',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}},body:JSON.stringify({{version:{stale_snapshot['version']},board_version:{stale_snapshot['board_version']},parent_id:{parent_id},position:0}})}})).status}}""");self.assertEqual(stale_status,409);other_context.close()
        role_status=page.evaluate("""async()=>{const s=await(await fetch('/api/session')).json();return(await fetch('/api/admin/workspace-memberships/u2?workspace_id=1',{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},body:JSON.stringify({role:'viewer'})})).status}""");self.assertEqual(role_status,200)
        viewer_context,viewer=self.login_page('u2');viewer.locator(f'[data-task="{parent_id}"]').click();viewer.locator('#addSubtaskBtn').wait_for(state='hidden')
        denied=viewer.evaluate(f"""async()=>{{const s=await(await fetch('/api/session')).json();const t=await(await fetch('/api/tasks/{child_id}')).json();const b=await(await fetch('/api/bootstrap')).json();return(await fetch('/api/tasks/{child_id}/parent',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}},body:JSON.stringify({{version:t.version,board_version:b.board.version,parent_id:null,position:0}})}})).status}}""");self.assertEqual(denied,403)
        viewer_context.close();context.close()

    def test_real_app_cross_board_mirror_formula_and_private_acl(self):
        context,page=self.login_page()
        setup=page.evaluate("""async()=>{const s=await(await fetch('/api/session')).json(),h={'Content-Type':'application/json','X-CSRF-Token':s.csrf_token};
          const call=async(url,method='GET',body)=>{const r=await fetch(url,{method,headers:h,body:body===undefined?undefined:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw Error(JSON.stringify(j));return j};
          let src=await call('/api/bootstrap'),source=src.groups[0].tasks[0];const board=await call('/api/workspaces/1/boards','POST',{name:'E2E relation target',access_type:'open'});const group=await call(`/api/boards/${board.id}/groups`,'POST',{name:'Target'});let target=await call(`/api/groups/${group.id}/tasks`,'POST',{title:'E2E source task'});let tb=await call(`/api/bootstrap?board_id=${board.id}`);const amount=await call(`/api/boards/${board.id}/fields`,'POST',{board_version:tb.board.version,name:'E2E amount',field_type:'number',config:{},options:[]});target=await call(`/api/tasks/${target.id}`,'PATCH',{version:target.version,field_values:{[amount.id]:7}});
          let v=src.board.version;const relation=await call(`/api/boards/${src.board.id}/fields`,'POST',{board_version:v,name:'E2E relation',field_type:'relation',config:{target_board_id:board.id,bidirectional:true},options:[]});v=relation.board_version;const mirror=await call(`/api/boards/${src.board.id}/fields`,'POST',{board_version:v,name:'E2E mirror',field_type:'mirror',config:{relation_field_id:relation.id,source_field_id:amount.id},options:[]});v=mirror.board_version;const formula=await call(`/api/boards/${src.board.id}/fields`,'POST',{board_version:v,name:'E2E formula',field_type:'formula',config:{expression:`SUM(f${mirror.id}) * 2`},options:[]});v=formula.board_version;await call(`/api/tasks/${source.id}/relations/${relation.id}`,'POST',{version:source.version,board_version:v,target_task_id:target.id,target_version:target.version});return{source:source.id,target:target.id,targetVersion:target.version,targetBoard:board.id,amount:amount.id,relation:relation.id,mirror:mirror.id,formula:formula.id}}""")
        page.reload();page.locator(f'[data-task="{setup["source"]}"]').wait_for();row=page.locator(f'[data-task="{setup["source"]}"]');self.assertIn("7",row.text_content());self.assertIn("14",row.text_content())
        row.click();page.get_by_text("跨看板关系与派生字段").wait_for();self.assertIn("E2E source task",page.locator(".relation-section").last.text_content());self.assertIn("14",page.locator(".relation-section").last.text_content());page.locator('[data-close="taskModal"]').evaluate("el=>el.click()")
        status=page.evaluate(f"""async()=>{{const s=await(await fetch('/api/session')).json();return(await fetch('/api/tasks/{setup['target']}',{{method:'PATCH',headers:{{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}},body:JSON.stringify({{version:{setup['targetVersion']},field_values:{{'{setup['amount']}':9}}}})}})).status}}""");self.assertEqual(status,200)
        page.reload();row=page.locator(f'[data-task="{setup["source"]}"]');row.wait_for();self.assertIn("9",row.text_content());self.assertIn("18",row.text_content())
        result=page.evaluate(f"""async()=>{{const s=await(await fetch('/api/session')).json(),h={{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}};let b=await(await fetch('/api/bootstrap?board_id={setup['targetBoard']}')).json();await fetch('/api/boards/{setup['targetBoard']}',{{method:'PATCH',headers:h,body:JSON.stringify({{version:b.board.version,access_type:'private'}})}});return(await fetch('/api/admin/workspace-memberships/u2?workspace_id=1',{{method:'PATCH',headers:h,body:JSON.stringify({{role:'viewer'}})}})).status}}""");self.assertEqual(result,200)
        viewer_context,viewer=self.login_page('u2');payload=viewer.evaluate(f"""async()=>{{const b=await(await fetch('/api/bootstrap?board_id=1')).json();const f=b.fields.find(x=>x.id==={setup['relation']});const targets=await fetch('/api/fields/{setup['relation']}/targets');return{{config:f.config,targetStatus:targets.status}}}}""");self.assertEqual(payload,{"config":{"unavailable":True},"targetStatus":403});viewer_context.close();context.close()


    def test_real_app_timeline_gantt_and_mobile_fallback(self):
        context,page=self.login_page();setup=page.evaluate("""async()=>{const s=await(await fetch('/api/session')).json(),h={'Content-Type':'application/json','X-CSRF-Token':s.csrf_token};const call=async(u,m='GET',b)=>{const r=await fetch(u,{method:m,headers:h,body:b===undefined?undefined:JSON.stringify(b)}),j=await r.json();if(!r.ok)throw Error(JSON.stringify(j));return j};let boot=await call('/api/bootstrap'),tasks=boot.groups.flatMap(g=>g.tasks).slice(0,3);const field=await call('/api/boards/1/fields','POST',{board_version:boot.board.version,name:'E2E schedule source',field_type:'timeline',config:{},options:[]});const ranges=[{start:'2026-08-01',end:'2026-08-03'},{start:'2026-08-04',end:'2026-08-06'},{start:'2026-10-01',end:'2026-10-01'}];for(let i=0;i<3;i++)tasks[i]={...tasks[i],...await call('/api/tasks/'+tasks[i].id,'PATCH',{version:tasks[i].version,field_values:{[field.id]:ranges[i]}})};const edge=await call('/api/tasks/'+tasks[1].id+'/dependencies','POST',{version:tasks[1].version,predecessor_id:tasks[0].id,predecessor_version:tasks[0].version,due_policy:'none'});const source={kind:'dynamic',id:field.id},base={scope:'shared',filter:{op:'and',children:[]},sort:[],visible_fields:[field.id],column_order:['title',field.id],is_default:false};const timeline=await call('/api/boards/1/views','POST',{...base,name:'E2E Timeline',view_type:'timeline',presentation:{version:1,source,scale:'week',show_dependencies:false,baseline:'disabled'}});const gantt=await call('/api/boards/1/views','POST',{...base,name:'E2E Gantt',view_type:'gantt',presentation:{version:1,source,scale:'week',show_dependencies:true,show_critical_path:true,baseline:'disabled'}});const filtered=await call('/api/boards/1/views','POST',{...base,name:'E2E Filtered Gantt',view_type:'gantt',filter:{op:'and',children:[{field:{kind:'core',key:'title'},operator:'equals',value:tasks[0].title}]},presentation:{version:1,source,scale:'week',show_dependencies:true,show_critical_path:true,baseline:'disabled'}});return{field:field.id,tasks:tasks.map(t=>t.id),timeline:timeline.id,gantt:gantt.id,filtered:filtered.id}}""")
        page.goto(f'{self.base}/?board=1&view={setup["timeline"]}');page.locator('.schedule-bar').first.wait_for();self.assertEqual(page.locator('.schedule-bar').count(),3);self.assertEqual(page.locator('#scheduleSource').input_value(),str(setup["field"]));self.assertEqual(page.locator('#scheduleScale').input_value(),'week');self.assertIn(f'view={setup["timeline"]}',page.url)
        page.locator('#scheduleScale').select_option('month');page.locator('.schedule-bar').first.wait_for();self.assertEqual(page.locator('#scheduleScale').input_value(),'month');page.reload();page.locator('.schedule-bar').first.wait_for();self.assertEqual(page.locator('#scheduleScale').input_value(),'month')
        page.once('dialog',lambda dialog:dialog.accept('copy'));page.locator('#viewBtn').click();page.wait_for_timeout(500);self.assertTrue(any('副本' in item.text_content() for item in page.locator('#viewSelect option').all()))
        page.once('dialog',lambda dialog:dialog.accept('set-default'));page.locator('#viewBtn').click();page.wait_for_timeout(500);page.goto(f'{self.base}/?board=1');page.locator('.schedule-bar').first.wait_for();self.assertEqual(page.locator('#scheduleScale').input_value(),'month')
        scroll=page.locator('.schedule-scroll');self.assertGreater(page.evaluate("el=>el.scrollWidth",scroll.element_handle()),page.evaluate("el=>el.clientWidth",scroll.element_handle()));page.locator('.schedule-toolbar button').click();self.assertGreaterEqual(page.evaluate("el=>el.scrollLeft",scroll.element_handle()),0)
        page.goto(f'{self.base}/?board=1&view={setup["gantt"]}');bar=page.locator(f'[data-schedule-bar="{setup["tasks"][0]}"]');bar.wait_for();box=bar.bounding_box();page.once('dialog',lambda dialog:dialog.dismiss());page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.mouse.move(box['x']+box['width']/2+12,box['y']+box['height']/2);page.mouse.up();page.locator('#toast',has_text='排期已更新').wait_for();page.reload();bar=page.locator(f'[data-schedule-bar="{setup["tasks"][0]}"]');bar.wait_for();self.assertIn('2026-08-02',bar.get_attribute('data-start'))
        box=bar.bounding_box();page.once('dialog',lambda dialog:dialog.dismiss());page.mouse.move(box['x']+box['width']-2,box['y']+box['height']/2);page.mouse.down();page.mouse.move(box['x']+box['width']+10,box['y']+box['height']/2);page.mouse.up();page.locator('#toast',has_text='排期已更新').wait_for();page.reload();self.assertEqual(page.locator(f'[data-schedule-bar="{setup["tasks"][0]}"]').get_attribute('data-start'),'2026-08-02');self.assertTrue(page.locator('.schedule-links path').count());self.assertTrue(page.locator('.schedule-bar.critical').count()>=2);self.assertEqual(page.locator('.schedule-bar.milestone').count(),1)
        page.goto(f'{self.base}/?board=1&view={setup["filtered"]}');page.locator('.schedule-bar').first.wait_for();self.assertEqual(page.locator('.schedule-bar').count(),1);self.assertEqual(page.locator('.schedule-links path').count(),0);page.goto(f'{self.base}/?board=1&view={setup["gantt"]}');page.locator('.schedule-bar').first.wait_for()
        stale=page.evaluate(f"""async()=>{{const t=await(await fetch('/api/tasks/{setup['tasks'][0]}')).json(),s=await(await fetch('/api/session')).json();const r=await fetch('/api/tasks/{setup['tasks'][0]}',{{method:'PATCH',headers:{{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}},body:JSON.stringify({{version:t.version,title:t.title+' stale'}})}});return r.status}}""");self.assertEqual(stale,200);bar=page.locator(f'[data-schedule-bar="{setup["tasks"][0]}"]');box=bar.bounding_box();page.once('dialog',lambda dialog:dialog.dismiss());page.mouse.move(box['x']+box['width']/2,box['y']+10);page.mouse.down();page.mouse.move(box['x']+box['width']/2+12,box['y']+10);page.mouse.up();page.locator('#toast',has_text='版本冲突').wait_for();page.locator('.schedule-bar').first.wait_for()
        role=page.evaluate("""async()=>{const s=await(await fetch('/api/session')).json();return(await fetch('/api/admin/workspace-memberships/u2?workspace_id=1',{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},body:JSON.stringify({role:'viewer'})})).status}""");self.assertEqual(role,200);unset=page.evaluate("""async()=>{const s=await(await fetch('/api/session')).json();return(await fetch('/api/boards/1/views/clear-personal-default',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},body:'{}'})).status}""");self.assertEqual(unset,200);context.close()
        mobile_context,mobile=self.login_page('u2',viewport={"width":390,"height":844});mobile.goto(f'{self.base}/?board=1&view={setup["timeline"]}');mobile.locator('.schedule-bar').first.wait_for();self.assertEqual(mobile.locator('[data-schedule-edit]').count(),0);denied=mobile.evaluate(f"""async()=>{{const s=await(await fetch('/api/session')).json(),b=await(await fetch('/api/bootstrap')).json(),t=await(await fetch('/api/tasks/{setup['tasks'][1]}')).json();return(await fetch('/api/tasks/{setup['tasks'][1]}/schedule',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token}},body:JSON.stringify({{version:t.version,board_version:b.board.version,source:{{kind:'dynamic',id:{setup['field']}}},start:'2026-09-01',end:'2026-09-02'}})}})).status}}""");self.assertEqual(denied,403);mobile_context.close()
        owner_context,owner=self.login_page(viewport={"width":390,"height":844});owner.goto(f'{self.base}/?board=1&view={setup["timeline"]}');edit=owner.locator(f'[data-schedule-edit="{setup["tasks"][1]}"]');edit.wait_for();answers=iter(['2026-09-01','2026-09-04',False]);owner.on('dialog',lambda dialog:dialog.accept(next(answers)) if dialog.type=='prompt' else dialog.dismiss());edit.click();owner.locator('#toast',has_text='排期已更新').wait_for();owner.reload();owner.locator(f'[data-schedule-bar="{setup["tasks"][1]}"][data-start="2026-09-01"]').wait_for();owner_context.close()


    def test_real_app_chart_views_and_dashboard_widgets(self):
        context,page=self.login_page();setup=page.evaluate("""async()=>{const s=await(await fetch('/api/session')).json(),h={'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},call=async(u,m='GET',b)=>{const r=await fetch(u,{method:m,headers:h,body:b===undefined?undefined:JSON.stringify(b)}),j=await r.json();if(!r.ok)throw Error(JSON.stringify(j));return j},base={scope:'shared',filter:{op:'and',children:[]},sort:[],visible_fields:[],column_order:['title'],is_default:false},views={};for(const type of ['bar','pie','stacked_bar']){const v=await call('/api/boards/1/views','POST',{...base,name:'E2E '+type,view_type:'chart',presentation:{version:1,chart_type:type,dimension:{kind:'core',key:'status'},metric:{op:'count'},date_bucket:'none',top_n:20,null_policy:'include'}});views[type]=v.id}const line=await call('/api/boards/1/views','POST',{...base,name:'E2E line',view_type:'chart',presentation:{version:1,chart_type:'line',dimension:{kind:'core',key:'due'},metric:{op:'count'},date_bucket:'month',top_n:20,null_policy:'include'}});views.line=line.id;let d=await call('/api/workspaces/1/dashboards','POST',{name:'E2E Dashboard',scope:'shared',global_filters:{version:1,by_source:{}}}),dv=d.version,source=await call('/api/dashboards/'+d.id+'/sources','POST',{dashboard_version:dv,source_key:'main',board_id:1,query:{version:1,filter:{op:'and',children:[]},sort:[]}});dv=source.dashboard_version;const spec={version:1,chart_type:'bar',dimension:{kind:'core',key:'status'},metric:{op:'count'},date_bucket:'none',top_n:20,null_policy:'include'},configs={number:{version:1,source_keys:['main'],spec:{...spec,dimension:{kind:'core',key:'board'}}},chart:{version:1,source_keys:['main'],spec},progress:{version:1,source_keys:['main'],complete_values:['已完成']},calendar:{version:1,source_keys:['main'],date_field:{kind:'core',key:'due'},limit:50},table:{version:1,source_keys:['main'],columns:['title','status'],limit:50}},widgets=[];let i=0;for(const [kind,config] of Object.entries(configs)){const w=await call('/api/dashboards/'+d.id+'/widgets','POST',{dashboard_version:dv,widget_type:kind,title:'E2E '+kind,config,x:0,y:i++*3,width:kind==='number'?3:6,height:3});dv=w.dashboard_version;widgets.push(w.id)}return{views,dashboard:d.id,widgets,dashboardVersion:dv}}""")
        for kind,view_id in setup['views'].items():
            page.goto(f'{self.base}/?board=1&view={view_id}');page.locator('.chart-data').wait_for();self.assertTrue(page.locator('.chart-data tbody tr').count());self.assertEqual(page.locator('#chartType').input_value(),kind)
        self.assertEqual(page.locator('#dashboardBtn').count(),0);page.evaluate("manageDashboards()");page.locator(f'[data-dashboard-open="{setup["dashboard"]}"]').click();page.locator('.dashboard-widget').first.wait_for();self.assertEqual(page.locator('.dashboard-widget').count(),5);page.locator('.dashboard-number').wait_for();self.assertEqual(page.locator('.widget-error').count(),0)
        widget=page.locator(f'[data-widget="{setup["widgets"][0]}"]');box=widget.bounding_box();self.assertIsNotNone(box);page.mouse.move(box['x']+18,box['y']+18);page.mouse.down();page.mouse.move(box['x']+118,box['y']+18);page.mouse.up();page.wait_for_function("id=>{const e=document.querySelector(`[data-widget=\"${id}\"]`);return e&&parseInt(e.style.gridColumn)!==1}",arg=str(setup["widgets"][0]));self.assertNotEqual(widget.evaluate("el=>parseInt(el.style.gridColumn)"),1)
        handle=page.locator(f'[data-widget-resize-handle="{setup["widgets"][0]}"]');resize=handle.bounding_box();self.assertIsNotNone(resize);hx=resize['x']+resize['width']/2;hy=resize['y']+resize['height']/2;page.mouse.move(hx,hy);page.mouse.down();page.mouse.move(hx+102,hy);page.mouse.up();page.wait_for_function("id=>{const e=document.querySelector(`[data-widget=\"${id}\"]`);return e&&!e.style.gridColumn.includes('span 3')}",arg=str(setup["widgets"][0]));self.assertFalse(page.locator(f'[data-widget="{setup["widgets"][0]}"]').evaluate("el=>el.style.gridColumn.includes('span 3')"))
        role=page.evaluate("""async()=>{const s=await(await fetch('/api/session')).json();return(await fetch('/api/admin/workspace-memberships/u2?workspace_id=1',{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},body:JSON.stringify({role:'viewer'})})).status}""");self.assertEqual(role,200);context.close()
        viewer_context,viewer=self.login_page('u2',viewport={"width":390,"height":844});viewer.locator('#mobileDashboardBtn').click();viewer.locator(f'[data-dashboard-open="{setup["dashboard"]}"]').click();viewer.locator('.dashboard-widget').first.wait_for();self.assertEqual(viewer.locator('.dashboard-widget').count(),5);self.assertEqual(viewer.locator('.dashboard-actions').count(),0);self.assertEqual(viewer.locator('[data-widget-move]').count(),0);self.assertLessEqual(viewer.evaluate("document.documentElement.scrollWidth"),390);viewer_context.close()


if __name__ == "__main__": unittest.main()

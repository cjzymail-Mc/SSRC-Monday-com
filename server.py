import json
import os
import socket
import sqlite3
import threading
import time
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from flowboard.database import SCHEMA_VERSION, migrate
from flowboard.service import ApiError, FlowboardService, require_object


ROOT = Path(__file__).resolve().parent
HOST = os.getenv("FLOWBOARD_HOST", "0.0.0.0")
PORT = int(os.getenv("FLOWBOARD_PORT", "8080"))
DB = os.getenv("FLOWBOARD_DB", str(ROOT / "flowboard.db"))
SESSION_COOKIE = "flowboard_session"
PUBLIC_PATHS = {"/", "/index.html", "/styles.css", "/auth.css", "/lifecycle.css", "/dashboard.css", "/dashboard-mobile.css", "/i12.css", "/i13.css", "/view-state.js", "/view-ui.js", "/schedule-ui.js", "/dashboard-ui.js", "/i12-ui.js", "/app.js"}


class PresenceRegistry:
    def __init__(self):self._lock=threading.Lock();self._users={}
    def enter(self,workspace_id,user_id):
        with self._lock:self._users[(workspace_id,user_id)]=self._users.get((workspace_id,user_id),0)+1
    def leave(self,workspace_id,user_id):
        with self._lock:
            key=(workspace_id,user_id);count=self._users.get(key,0)-1
            if count>0:self._users[key]=count
            else:self._users.pop(key,None)
    def list(self,workspace_id):
        with self._lock:return sorted(user for (wid,user),count in self._users.items() if wid==workspace_id and count>0)


PRESENCE=PresenceRegistry()


class FlowboardHTTPServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):self.stop_event=threading.Event();super().__init__(*args,**kwargs)
    def shutdown(self):self.stop_event.set();return super().shutdown()


class Handler(SimpleHTTPRequestHandler):
    service = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, status, payload, *, cookie=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def read_body_bytes(self):
        if hasattr(self, "_body_bytes"):
            return self._body_bytes
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(400, "INVALID_REQUEST", "Content-Length 无效")
        if length > 2_100_000:
            raise ApiError(413, "REQUEST_TOO_LARGE", "请求内容过大")
        self._body_bytes = self.rfile.read(length)
        return self._body_bytes

    def body(self):
        try:
            return require_object(json.loads(self.read_body_bytes() or b"{}"))
        except ApiError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ApiError(400, "INVALID_JSON", "请求正文必须是有效 JSON")

    def token(self):
        raw = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        try:
            jar.load(raw)
            return jar[SESSION_COOKIE].value if SESSION_COOKIE in jar else None
        except cookies.CookieError:
            return None

    def session_cookie(self, token, *, clear=False):
        jar = cookies.SimpleCookie()
        jar[SESSION_COOKIE] = "" if clear else token
        jar[SESSION_COOKIE]["path"] = "/"
        jar[SESSION_COOKIE]["httponly"] = True
        jar[SESSION_COOKIE]["samesite"] = "Lax"
        if os.getenv("FLOWBOARD_SECURE_COOKIE") == "1":
            jar[SESSION_COOKIE]["secure"] = True
        jar[SESSION_COOKIE]["max-age"] = 0 if clear else 12 * 60 * 60
        return jar.output(header="").strip()

    def current_user(self, *, csrf=False):
        user = self.service.authenticate(self.token())
        if csrf:
            self.service.verify_csrf(user, self.headers.get("X-CSRF-Token"))
        return user

    def dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if method in {"POST", "PATCH", "DELETE"}:
            self.read_body_bytes()

        if method == "POST" and path == "/api/auth/login":
            data = self.body()
            username = data.get("username")
            password = data.get("password")
            if not isinstance(username, str) or not isinstance(password, str):
                raise ApiError(422, "VALIDATION_ERROR", "username and password are required")
            token, csrf, user = self.service.login(username.strip(), password)
            return 200, {"user": user, "csrf_token": csrf}, self.session_cookie(token)

        if method == "GET" and path == "/api/health":
            return 200, {"status":"ok","schema_version":SCHEMA_VERSION}, None

        if method == "GET" and path == "/api/session":
            user = self.current_user()
            return 200, self.service.session_info(user), None

        if method == "POST" and path == "/api/auth/logout":
            user = self.current_user(csrf=True)
            del user
            self.service.logout(self.token())
            return 200, {"ok": True}, self.session_cookie("", clear=True)

        user = self.current_user(csrf=method in {"POST", "PATCH", "DELETE"})
        data = self.body() if method in {"POST", "PATCH", "DELETE"} else None

        if method == "GET" and path == "/api/bootstrap":
            board_id = query.get("board_id", [None])[0]
            return 200, self.service.bootstrap(user, int(board_id) if board_id else None), None
        parts = path.strip("/").split("/")

        if len(parts) == 4 and parts[:2] == ["api", "workspaces"] and parts[3] == "boards":
            workspace_id = int(parts[2])
            if method == "GET":
                return 200, self.service.list_boards(user, workspace_id, query.get("state", ["active"])[0]), None
            if method == "POST":
                return 201, self.service.create_board(user, workspace_id, data), None
        if len(parts)==4 and parts[:2]==["api","workspaces"] and parts[3]=="notifications":
            workspace_id=int(parts[2])
            if method=="GET":return 200,self.service.notifications(user,workspace_id,after=query.get("after",[0])[0],limit=query.get("limit",[50])[0]),None
        if len(parts)==5 and parts[:2]==["api","workspaces"] and parts[3:]==["notifications","read-all"] and method=="POST":
            return 200,self.service.read_all_notifications(user,int(parts[2])),None
        if len(parts)==4 and parts[:2]==["api","workspaces"] and parts[3]=="search" and method=="GET":
            return 200,self.service.global_search(user,int(parts[2]),query.get("q",[""])[0],after=query.get("after",[0])[0],limit=query.get("limit",[30])[0]),None
        if len(parts)==5 and parts[:2]==["api","workspaces"] and parts[3:]==["tasks","batch"] and method=="POST":
            return 200,self.service.batch_tasks(user,int(parts[2]),data),None
        if len(parts)==5 and parts[:2]==["api","workspaces"] and parts[3:]==["events","poll"] and method=="GET":
            payload=self.service.realtime_poll(user,int(parts[2]),cursor=query.get("cursor",[0])[0],limit=query.get("limit",[100])[0]);payload["online"]=PRESENCE.list(int(parts[2]));return 200,payload,None
        if len(parts)==5 and parts[:3]==["api","admin","workspaces"] and parts[4]=="audit" and method=="GET":
            workspace_id=int(parts[3])
            return 200,self.service.audit(user,workspace_id,after=query.get("after",[0])[0],limit=query.get("limit",[50])[0],action=query.get("action",[None])[0]),None
        if len(parts)==5 and parts[:3]==["api","admin","workspaces"] and parts[4]=="backups":
            workspace_id=int(parts[3])
            if method=="GET":return 200,self.service.backups(user,workspace_id),None
            if method=="POST":return 201,self.service.create_admin_backup(user,workspace_id),None
        if len(parts)==6 and parts[:3]==["api","admin","workspaces"] and parts[4]=="backups" and method=="POST":
            return 200,self.service.verify_admin_backup(user,int(parts[3]),parts[5]),None
        if len(parts) == 4 and parts[:2] == ["api", "workspaces"] and parts[3] == "trash" and method == "GET":
            return 200, self.service.trash(user, int(parts[2])), None
        if len(parts)==5 and parts[:2]==["api","workspaces"] and parts[3:]==["trash","purge-preview"] and method in {"GET","POST"}:
            return 200,self.service.trash_purge_preview(user,int(parts[2])),None
        if len(parts)==5 and parts[:2]==["api","workspaces"] and parts[3:]==["trash","purge"] and method=="POST":
            return 200,self.service.trash_purge(user,int(parts[2]),data),None
        if len(parts) == 4 and parts[:2] == ["api", "workspaces"] and parts[3] == "templates":
            workspace_id=int(parts[2])
            if method=="GET":return 200,self.service.list_templates(user,workspace_id,query.get("include_deleted",["0"])[0]=="1"),None
            if method=="POST":return 201,self.service.create_template(user,workspace_id,data),None
        if len(parts) == 4 and parts[:2] == ["api", "workspaces"] and parts[3] == "dashboards":
            workspace_id=int(parts[2])
            if method=="GET":return 200,self.service.list_dashboards(user,workspace_id,query.get("include_deleted",["0"])[0]=="1"),None
            if method=="POST":return 201,self.service.create_dashboard(user,workspace_id,data),None

        if len(parts)>=3 and parts[:2]==["api","templates"]:
            template_id=int(parts[2])
            if len(parts)==3:
                if method=="PATCH":return 200,self.service.update_template(user,template_id,data),None
                if method=="DELETE":return 200,self.service.delete_template(user,template_id,data),None
            if len(parts)==4 and method=="POST":
                if parts[3]=="instantiate":return 201,self.service.instantiate_template(user,template_id,data),None
                if parts[3]=="restore":return 200,self.service.restore_template(user,template_id,data),None

        if len(parts) >= 3 and parts[:2] == ["api", "boards"]:
            board_id = int(parts[2])
            if len(parts) == 3:
                if method == "GET": return 200, self.service.bootstrap(user, board_id), None
                if method == "PATCH": return 200, self.service.update_board(user, board_id, data), None
                if method == "DELETE": return 200, self.service.delete_board(user, board_id, data), None
            if len(parts) == 4 and parts[3] == "groups" and method == "POST": return 201, self.service.create_group(user, board_id, data), None
            if len(parts) == 4 and parts[3] == "fields" and method == "POST": return 201, self.service.create_field(user, board_id, data), None
            if len(parts) == 5 and parts[3:] == ["fields","reorder"] and method == "POST": return 200, self.service.reorder_fields(user,board_id,data), None
            if len(parts) == 4 and parts[3] == "query" and method == "POST": return 200, self.service.query_tasks(user,board_id,data), None
            if len(parts) == 5 and parts[3:] == ["imports","preview"] and method == "POST": return 201,self.service.preview_import(user,board_id,data),None
            if len(parts) == 5 and parts[3:] == ["imports","commit"] and method == "POST": return 201,self.service.commit_import(user,board_id,data),None
            if len(parts) == 4 and parts[3] == "export" and method == "POST": return 200,self.service.export_board(user,board_id,data),None
            if len(parts) == 4 and parts[3] == "schedule" and method == "POST": return 200,self.service.schedule(user,board_id,data),None
            if len(parts) == 4 and parts[3] == "aggregate" and method == "POST": return 200,self.service.aggregate_board(user,board_id,data),None
            if len(parts) == 4 and parts[3] == "views":
                if method == "GET": return 200, self.service.list_views(user,board_id), None
                if method == "POST": return 201, self.service.create_view(user,board_id,data), None
            if len(parts) == 5 and parts[3:] == ["views","clear-personal-default"] and method == "POST": return 200, self.service.clear_personal_default(user,board_id,data), None
            if len(parts) == 4 and parts[3] == "activity" and method == "GET": return 200, self.service.activity(user, board_id), None
            if len(parts) == 4 and parts[3] == "archived" and method == "GET": return 200, self.service.archived(user, board_id), None
            if len(parts) == 4 and method == "POST":
                if parts[3] == "copy": return 201, self.service.copy_board(user, board_id, data), None
                return 200, self.service.board_command(user, board_id, parts[3], data), None

        if len(parts) >= 3 and parts[:2] == ["api", "groups"]:
            group_id = int(parts[2])
            if len(parts) == 3:
                if method == "GET": return 200, self.service.group_detail(user, group_id), None
                if method == "PATCH": return 200, self.service.update_group(user, group_id, data), None
                if method == "DELETE": return 200, self.service.delete_group(user, group_id, data), None
            if len(parts) == 4 and parts[3] == "tasks" and method == "POST": return 201, self.service.create_task(user, group_id, data), None
            if len(parts) == 4 and method == "POST":
                if parts[3] == "copy": return 201, self.service.copy_group(user, group_id, data), None
                if parts[3] == "move": return 200, self.service.move_group(user, group_id, data), None
                return 200, self.service.group_command(user, group_id, parts[3], data), None

        if len(parts) >= 3 and parts[:2] == ["api", "tasks"]:
            task_id = int(parts[2])
            if len(parts) == 3:
                if method == "GET": return 200, self.service.task_detail(user, task_id), None
                if method == "PATCH": return 200, self.service.update_task(user, task_id, data), None
                if method == "DELETE": return 200, self.service.delete_task(user, task_id, data), None
            if len(parts) == 4 and parts[3] == "comments" and method == "POST": return 201, self.service.create_comment(user, task_id, data), None
            if len(parts) == 4 and parts[3] == "subscription" and method == "POST": return 200, self.service.set_subscription(user, task_id, data), None
            if len(parts) == 4 and parts[3] == "attachments" and method == "POST": return 201, self.service.create_attachment(user, task_id, data), None
            if len(parts) == 4 and parts[3] == "activity" and method == "GET":
                detail = self.service.task_detail(user, task_id)
                return 200, detail["activity"], None
            if len(parts) == 5 and parts[3] == "dependencies" and method == "DELETE":
                return 200, self.service.delete_dependency(user,task_id,int(parts[4]),data), None
            if len(parts) == 5 and parts[3] == "relations":
                if method == "POST": return 201,self.service.add_task_relation(user,task_id,int(parts[4]),data),None
                if method == "DELETE": return 200,self.service.delete_task_relation(user,task_id,int(parts[4]),data),None
            if len(parts) == 4 and method == "POST":
                if parts[3] == "copy": return 201, self.service.copy_task(user, task_id, data), None
                if parts[3] == "move": return 200, self.service.move_task(user, task_id, data), None
                if parts[3] == "kanban-move": return 200, self.service.kanban_move_task(user, task_id, data), None
                if parts[3] == "parent": return 200, self.service.set_task_parent(user,task_id,data), None
                if parts[3] == "dependencies": return 201, self.service.create_dependency(user,task_id,data), None
                if parts[3] == "schedule": return 200,self.service.update_schedule(user,task_id,data),None
                return 200, self.service.task_command(user, task_id, parts[3], data), None

        if len(parts)==3 and parts[:2]==["api","comments"]:
            comment_id=int(parts[2])
            if method=="PATCH": return 200,self.service.update_comment(user,comment_id,data),None
            if method=="DELETE": return 200,self.service.delete_comment(user,comment_id,data),None
        if len(parts)==3 and parts[:2]==["api","attachments"] and method=="DELETE": return 200,self.service.delete_attachment(user,int(parts[2]),data),None
        if len(parts)==3 and parts[:2]==["api","notifications"] and method=="PATCH":return 200,self.service.read_notification(user,int(parts[2]),data),None

        if len(parts) >= 3 and parts[:2] == ["api", "fields"]:
            field_id = int(parts[2])
            if len(parts) == 3 and method == "PATCH": return 200, self.service.update_field(user, field_id, data), None
            if len(parts) == 4 and parts[3] == "targets" and method == "GET": return 200,self.service.relation_targets(user,field_id,query.get("q",[""])[0]),None
            if len(parts) == 4 and method == "POST": return 200, self.service.field_command(user, field_id, parts[3], data), None

        if len(parts) >= 3 and parts[:2] == ["api","views"]:
            view_id=int(parts[2])
            if len(parts)==3:
                if method=="PATCH": return 200,self.service.update_view(user,view_id,data),None
                if method=="DELETE": return 200,self.service.delete_view(user,view_id,data),None
            if len(parts)==4 and parts[3]=="copy" and method=="POST": return 201,self.service.copy_view(user,view_id,data),None

        if len(parts)>=3 and parts[:2]==["api","dashboards"]:
            dashboard_id=int(parts[2])
            if len(parts)==3:
                if method=="GET":return 200,self.service.get_dashboard(user,dashboard_id),None
                if method=="PATCH":return 200,self.service.update_dashboard(user,dashboard_id,data),None
                if method=="DELETE":return 200,self.service.dashboard_command(user,dashboard_id,"delete",data),None
            if len(parts)==4 and method=="POST":
                if parts[3]=="copy":return 201,self.service.copy_dashboard(user,dashboard_id,data),None
                if parts[3]=="restore":return 200,self.service.dashboard_command(user,dashboard_id,"restore",data),None
                if parts[3]=="sources":return 201,self.service.add_dashboard_source(user,dashboard_id,data),None
                if parts[3]=="widgets":return 201,self.service.add_dashboard_widget(user,dashboard_id,data),None
            if len(parts)==5 and parts[3]=="sources":
                source_id=int(parts[4])
                if method=="PATCH":return 200,self.service.update_dashboard_source(user,dashboard_id,source_id,data),None
                if method=="DELETE":return 200,self.service.dashboard_source_command(user,dashboard_id,source_id,"delete",data),None
            if len(parts)==6 and parts[3]=="sources" and method=="POST":return 200,self.service.dashboard_source_command(user,dashboard_id,int(parts[4]),parts[5],data),None
            if len(parts)==5 and parts[3]=="widgets":
                widget_id=int(parts[4])
                if method=="PATCH":return 200,self.service.update_dashboard_widget(user,dashboard_id,widget_id,data),None
                if method=="DELETE":return 200,self.service.dashboard_widget_command(user,dashboard_id,widget_id,"delete",data),None
            if len(parts)==6 and parts[3]=="widgets":
                widget_id=int(parts[4])
                if parts[5]=="data" and method=="POST":return 200,self.service.dashboard_widget_data(user,dashboard_id,widget_id),None
                if method=="POST":return (201 if parts[5]=="copy" else 200),self.service.dashboard_widget_command(user,dashboard_id,widget_id,parts[5],data),None

        # Compatibility aliases from iteration 1.
        if method == "POST" and path == "/api/tasks":
            group_id = data.pop("group_id", None)
            return 201, self.service.create_task(user, group_id, data), None
        if method == "POST" and path == "/api/groups":
            board_id = data.pop("board_id", None)
            return 201, self.service.create_group(user, board_id, data), None
        if method == "POST" and path == "/api/comments":
            task_id = data.pop("task_id", None)
            return 201, self.service.create_comment(user, task_id, data), None
        if method == "GET" and path == "/api/admin/workspace-memberships":
            workspace_id = int(query.get("workspace_id", [1])[0])
            return 200, self.service.memberships(user, workspace_id), None
        if method == "PATCH" and path.startswith("/api/admin/workspace-memberships/"):
            workspace_id = int(query.get("workspace_id", [1])[0])
            return 200, self.service.update_membership(user, workspace_id, path.rsplit("/", 1)[-1], data.get("role")), None
        raise ApiError(404, "NOT_FOUND", "接口不存在")

    @staticmethod
    def path_id(path):
        try:
            return int(path.rsplit("/", 1)[-1])
        except ValueError:
            raise ApiError(404, "NOT_FOUND", "资源不存在")

    def api(self, method):
        try:
            status, payload, cookie = self.dispatch(method)
            self.send_json(status, payload, cookie=cookie)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            return
        except ApiError as error:
            try:self.send_json(error.status, error.payload())
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):return
        except (ValueError, sqlite3.IntegrityError):
            self.send_json(422, ApiError(422, "VALIDATION_ERROR", "请求数据无效").payload())
        except Exception as error:
            self.log_error("Unhandled error: %r", error)
            try:self.send_json(500, ApiError(500, "INTERNAL_ERROR", "服务器内部错误").payload())
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):return

    def do_GET(self):
        path = urlparse(self.path).path
        parts=path.strip("/").split("/")
        if len(parts)==5 and parts[:2]==["api","workspaces"] and parts[3:]==["events","stream"]:
            try:
                user=self.current_user();workspace_id=int(parts[2]);query=parse_qs(urlparse(self.path).query);cursor=query.get("cursor",[self.headers.get("Last-Event-ID","0")])[0];limit=query.get("limit",[100])[0]
                self.service.realtime_poll(user,workspace_id,cursor=cursor,limit=limit)
                self.send_response(200);self.send_header("Content-Type","text/event-stream; charset=utf-8");self.send_header("Cache-Control","no-cache, no-store");self.send_header("Connection","close");self.end_headers();PRESENCE.enter(workspace_id,user["id"])
                try:
                    deadline=time.monotonic()+15
                    while time.monotonic()<deadline and not self.server.stop_event.is_set():
                        previous_cursor=cursor;payload=self.service.realtime_poll(user,workspace_id,cursor=cursor,limit=limit);payload["online"]=PRESENCE.list(workspace_id);cursor=payload["cursor"]
                        if payload["events"] or int(cursor)>int(previous_cursor):
                            raw=json.dumps(payload,ensure_ascii=False);self.wfile.write(f"id: {cursor}\nevent: update\ndata: {raw}\n\n".encode("utf-8"));self.wfile.flush();break
                        self.wfile.write(f": heartbeat {int(time.time())}\n\n".encode("utf-8"));self.wfile.flush();time.sleep(.5)
                finally:PRESENCE.leave(workspace_id,user["id"])
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,OSError):pass
            except ApiError as error:self.send_json(error.status,error.payload())
            return
        if len(parts)==5 and parts[:3]==["api","admin","workspaces"] and parts[4]=="audit.csv":
            try:
                user=self.current_user();raw=self.service.audit_csv(user,int(parts[3]),action=parse_qs(urlparse(self.path).query).get("action",[None])[0]).encode("utf-8-sig");self.send_response(200);self.send_header("Content-Type","text/csv; charset=utf-8");self.send_header("Content-Disposition","attachment; filename=audit.csv");self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(raw)
            except ApiError as error:self.send_json(error.status,error.payload())
            return
        if len(parts)==4 and parts[:2]==["api","attachments"] and parts[3]=="content":
            try:
                preview=parse_qs(urlparse(self.path).query).get("preview",["0"])[0]=="1";user=self.current_user(); meta,raw=self.service.attachment_content(user,int(parts[2]),preview=preview); self.send_response(200)
                self.send_header("Content-Type",meta["content_type"]); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","private, no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Content-Security-Policy","default-src 'none'; img-src 'self'; style-src 'none'; sandbox")
                disposition="inline" if preview else "attachment";self.send_header("Content-Disposition",f"{disposition}; filename*=UTF-8''{quote(meta['original_name'],safe='')}");self.end_headers(); self.wfile.write(raw)
            except ApiError as error: self.send_json(error.status,error.payload())
            return
        if path.startswith("/api/"):
            return self.api("GET")
        if self.is_public_path(path):
            return super().do_GET()
        self.send_json(404, ApiError(404, "NOT_FOUND", "资源不存在").payload())

    @staticmethod
    def is_public_path(path):
        return path in PUBLIC_PATHS

    def do_HEAD(self):
        path = urlparse(self.path).path
        if self.is_public_path(path):
            return super().do_HEAD()
        self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def do_POST(self):
        return self.api("POST")

    def do_PATCH(self):
        return self.api("PATCH")

    def do_DELETE(self):
        return self.api("DELETE")

    def do_OPTIONS(self):
        self.send_json(405, ApiError(405, "METHOD_NOT_ALLOWED", "不支持跨站请求").payload())


def create_server(host=HOST, port=PORT, db_path=DB):
    backup = migrate(db_path)
    if backup:
        print(f"Pre-migration backup: {backup}")
    handler = type("FlowboardHandler", (Handler,), {"service": FlowboardService(db_path)})
    return FlowboardHTTPServer((host, port), handler)


def lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


if __name__ == "__main__":
    server = create_server()
    print(f"Flowboard running at http://localhost:{PORT}")
    print(f"LAN access: http://{lan_ip()}:{PORT}")
    if os.getenv("FLOWBOARD_INITIAL_PASSWORD") is None:
        print("WARNING: initial password is 'flowboard'; set FLOWBOARD_INITIAL_PASSWORD before first migration.")
    server.serve_forever()

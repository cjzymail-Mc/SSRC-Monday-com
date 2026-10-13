# -*- coding: utf-8 -*-
# 端口探测探针：在多个候选端口上监听 HTTP，用于实测 GPO 防火墙实际放行哪些入站端口。
# 每个端口对任意路径响应 "PORT-PROBE <port> OK"，与彩排服务(8080)互不影响。
# 授权来源：用户 2026-10-12 16:1x 明确指示"换一个端口"；纯临时监听，不改防火墙/系统配置。
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORTS = [554, 2869, 5357, 7250, 9955, 10246, 10247, 23554]


def make_handler(port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = f"PORT-PROBE {port} OK\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            print(f"[{port}] {self.client_address[0]} {fmt % args}", flush=True)
    return Handler


def serve(port):
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(port))
        print(f"listening on 0.0.0.0:{port}", flush=True)
        srv.serve_forever()
    except OSError as e:
        print(f"bind FAILED on {port}: {e}", flush=True)


for p in PORTS:
    threading.Thread(target=serve, args=(p,), daemon=True).start()

threading.Event().wait()

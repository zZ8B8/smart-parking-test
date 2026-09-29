# -*- coding: utf-8 -*-
"""智能停车管理系统 · HTTP 接口层

用标准库 http.server 实现，零第三方依赖：

    python sut/server.py            # 监听 127.0.0.1:5002
    python sut/server.py 8080       # 指定端口

统一响应格式：
    成功  {"code": "OK", "data": ...}
    失败  {"code": "错误码", "message": "错误描述"}
"""
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

if __package__ in (None, ""):
    sys.path.insert(0, __file__.rsplit("sut", 1)[0])
    from sut import service
    from sut.service import BizError
else:
    from . import service
    from .service import BizError


DEFAULT_PORT = 5002


class Router(object):
    """极简路由：把 (method, path_pattern) 映射到处理函数。"""

    def __init__(self):
        self.rules = []

    def add(self, method, pattern, handler):
        regex = re.compile("^" + pattern.replace("{plate}", "(?P<plate>[^/]+)")
                                        .replace("{id}", "(?P<id>[^/]+)") + "$")
        self.rules.append((method, regex, handler))

    def match(self, method, path):
        for m, regex, handler in self.rules:
            if m != method:
                continue
            found = regex.match(path)
            if found:
                return handler, found.groupdict()
        return None, None


router = Router()


def route(method, pattern):
    def wrapper(func):
        router.add(method, pattern, func)
        return func
    return wrapper


# --------------------------------------------------------------------------
# 接口实现
# --------------------------------------------------------------------------
@route("GET", "/health")
def health(ctx):
    return {"status": "UP"}


@route("GET", "/api/lot/summary")
def api_lot_summary(ctx):
    return service.lot_summary()


@route("GET", "/api/spots")
def api_spots(ctx):
    query = ctx["query"]
    return service.list_spots(
        status=query.get("status", [None])[0],
        spot_type=query.get("type", [None])[0],
    )


@route("POST", "/api/vehicles/entry")
def api_entry(ctx):
    body = ctx["body"]
    return service.entry(body.get("plate"), body.get("spotType"))


@route("POST", "/api/vehicles/exit")
def api_exit(ctx):
    return service.exit_vehicle(ctx["body"].get("plate"))


@route("GET", "/api/tickets")
def api_tickets(ctx):
    query = ctx["query"]
    return service.list_tickets(
        plate=query.get("plate", [None])[0],
        status=query.get("status", [None])[0],
    )


@route("GET", "/api/tickets/{id}")
def api_ticket_detail(ctx):
    return service.get_ticket(ctx["params"]["id"])


@route("POST", "/api/cards")
def api_issue_card(ctx):
    body = ctx["body"]
    return service.issue_card(body.get("plate"), body.get("validUntil"))


@route("GET", "/api/cards/{plate}")
def api_get_card(ctx):
    return service.get_card(ctx["params"]["plate"])


# --------------------------------------------------------------------------
# HTTP 处理
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise BizError("INVALID_JSON", "请求体不是合法的 JSON", 400)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        # 路径参数可能是 URL 编码的（如中文车牌），匹配前先解码
        handler, params = router.match(method, unquote(parsed.path))
        if handler is None:
            self._send(404, {"code": "NOT_FOUND", "message": "接口不存在"})
            return

        try:
            ctx = {
                "body": self._read_body(),
                "query": parse_qs(parsed.query),
                "params": params,
                "method": method,
            }
            data = handler(ctx)
            self._send(200, {"code": "OK", "data": data})
        except BizError as e:
            self._send(e.http_status, {"code": e.code, "message": e.message})
        except Exception as e:                       # noqa: BLE001
            self._send(500, {"code": "INTERNAL_ERROR", "message": str(e)})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


def create_server(port=DEFAULT_PORT, verbose=False):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.verbose = verbose
    return httpd


def run_in_thread(port=0, verbose=False):
    """在后台线程启动服务，返回 (httpd, base_url)。"""
    httpd = create_server(port, verbose)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    httpd = create_server(port, verbose=True)
    print("智能停车管理系统接口服务已启动：http://127.0.0.1:%d" % httpd.server_address[1])
    print("健康检查：/health   接口文档：docs/接口文档.md")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()

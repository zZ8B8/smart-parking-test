# -*- coding: utf-8 -*-
"""测试用接口客户端。

为什么不用 requests：不想让测试套件依赖第三方库，
用标准库 urllib 就够了，克隆下来装 Flask + PyMySQL 就能跑。

注意：URL 里可能带中文（车牌），urllib 不允许请求行出现非 ASCII 字符，
所以统一用 quote 编码一次。
"""
import json
import urllib.error
import urllib.parse
import urllib.request


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__("%s %s: %s" % (status, code, message))
        self.status = status
        self.code = code
        self.message = message


class ApiClient(object):
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------
    #  底层
    # ------------------------------------------------------------
    def request(self, method, path, body=None):
        url = self.base_url + urllib.parse.quote(path, safe="/?=&%#")
        data = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                return payload.get("data")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = {"code": "HTTP_%d" % exc.code, "message": raw}
            raise ApiError(exc.code, payload.get("code"), payload.get("message"))

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body=None):
        return self.request("POST", path, body if body is not None else {})

    # ------------------------------------------------------------
    #  业务封装
    # ------------------------------------------------------------
    def entry(self, plate, spot_type=None):
        return self.post("/api/vehicles/entry",
                         {"plate": plate, "spotType": spot_type})

    def exit(self, plate):
        return self.post("/api/vehicles/exit", {"plate": plate})

    def summary(self):
        return self.get("/api/lot/summary")

    def spots(self, status=None, spot_type=None):
        params = []
        if status:
            params.append("status=" + status)
        if spot_type:
            params.append("type=" + spot_type)
        q = ("?" + "&".join(params)) if params else ""
        return self.get("/api/spots" + q)

    def tickets(self, plate=None, status=None):
        params = []
        if plate:
            params.append("plate=" + urllib.parse.quote(plate))
        if status:
            params.append("status=" + status)
        q = ("?" + "&".join(params)) if params else ""
        return self.get("/api/tickets" + q)

    def ticket(self, ticket_id):
        return self.get("/api/tickets/%s" % ticket_id)

    def issue_card(self, plate, valid_until):
        return self.post("/api/cards", {"plate": plate, "validUntil": valid_until})

    def get_card(self, plate):
        return self.get("/api/cards/" + urllib.parse.quote(plate))

    def cards(self):
        return self.get("/api/cards")

    def consistency(self):
        return self.get("/api/consistency")

    # ------------------------------------------------------------
    #  测试时钟
    # ------------------------------------------------------------
    def advance_clock(self, seconds):
        return self.post("/api/dev/clock", {"advance": seconds})

    def reset_clock(self):
        return self.post("/api/dev/clock", {"reset": True})

    def clock(self):
        return self.get("/api/dev/clock")

    # ------------------------------------------------------------
    #  便捷断言辅助
    # ------------------------------------------------------------
    def open_ticket_count(self):
        return self.tickets(status="PARKING")["total"]

    def occupied_spot_count(self):
        return self.spots(status="OCCUPIED")["total"]

    def free_spot_count(self):
        return self.spots(status="FREE")["total"]

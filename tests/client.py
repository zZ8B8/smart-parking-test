# -*- coding: utf-8 -*-
"""极简 HTTP 测试客户端（标准库实现，不依赖 requests）

让测试只关注业务断言，不用重复写 urllib 的样板代码。
"""
import json
import urllib.error
import urllib.request


class ApiResponse(object):
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    @property
    def code(self):
        return self.payload.get("code")

    @property
    def message(self):
        return self.payload.get("message")

    @property
    def data(self):
        return self.payload.get("data")

    def __repr__(self):
        return "<ApiResponse %s %s>" % (
            self.status, json.dumps(self.payload, ensure_ascii=False))


class ApiClient(object):
    def __init__(self, base_url):
        self.base_url = base_url

    def request(self, method, path, body=None, timeout=15):
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return ApiResponse(resp.status, json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            return ApiResponse(e.code, json.loads(e.read().decode("utf-8")))

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body, **kw)

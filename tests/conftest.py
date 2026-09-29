# -*- coding: utf-8 -*-
"""pytest 公共装置（fixture）

- 整个测试会话共用一个 HTTP 服务实例（随机空闲端口）；
- 每个用例开始前重置内存数据与时钟，用例之间互不污染。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sut import server as sut_server          # noqa: E402
from sut import service                       # noqa: E402
from sut.store import store                   # noqa: E402
from tests.client import ApiClient            # noqa: E402


@pytest.fixture(scope="session")
def api_base():
    """启动服务，会话结束后关闭。port=0 由系统分配空闲端口。"""
    httpd, base_url = sut_server.run_in_thread(port=0)
    yield base_url
    httpd.shutdown()


@pytest.fixture(autouse=True)
def fresh_data():
    """每个用例前清空数据并重置时钟。"""
    store.reset()
    service.reset_clock()
    yield
    service.reset_clock()


@pytest.fixture
def api(api_base):
    """HTTP 客户端。"""
    return ApiClient(api_base)


@pytest.fixture
def park(api):
    """车辆入场，返回响应。"""
    def _park(plate="津A12345", spot_type=None):
        body = {"plate": plate}
        if spot_type:
            body["spotType"] = spot_type
        return api.post("/api/vehicles/entry", body)

    return _park


@pytest.fixture
def leave(api):
    """车辆出场，返回响应。"""
    def _leave(plate="津A12345"):
        return api.post("/api/vehicles/exit", {"plate": plate})

    return _leave


@pytest.fixture
def advance():
    """把系统时钟前移若干秒。"""
    def _advance(seconds):
        service.advance_clock(seconds)

    return _advance


@pytest.fixture
def free_spots(api):
    """当前空闲车位数。"""
    def _free():
        return api.get("/api/lot/summary").data["free"]

    return _free

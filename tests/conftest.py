# -*- coding: utf-8 -*-
"""pytest 公共夹具。

关键设计：
1. session 级的 server 夹具：整个测试会话只起一次被测服务，
   用 werkzeug 的 make_server 在后台线程跑，跑完自动关闭。
   —— 所以执行 pytest 前**不需要**手工启动 app.py。
2. autouse 的 fresh_data 夹具：每条用例前重置数据库 + 时钟，
   保证用例之间互不影响、可重复执行。
3. quick 配置：把并发延迟调小，让大部分用例跑得快；
   需要放大竞态窗口的并发用例自己再调大（见 wide_race_window）。
"""
import os
import sys
import threading

import pymysql
import pytest
from werkzeug.serving import make_server

# 让测试能 import 到项目根目录下的模块（config / app / init_db ...）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config          # noqa: E402
import init_db         # noqa: E402
import service         # noqa: E402
from app import app    # noqa: E402
from tests.client import ApiClient  # noqa: E402

TEST_PORT = 5012
BASE_URL = "http://127.0.0.1:%d" % TEST_PORT


# ==================================================================
#  被测服务
# ==================================================================
@pytest.fixture(scope="session")
def server():
    """在后台线程起一个真实的 HTTP 服务（多线程模式，支持并发用例）。"""
    httpd = make_server("127.0.0.1", TEST_PORT, app, threaded=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield BASE_URL
    httpd.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def api(server):
    return ApiClient(server)


# ==================================================================
#  数据重置
# ==================================================================
@pytest.fixture(autouse=True)
def fresh_data():
    """每条用例开始前：重建初始数据 + 时钟归零 + 延迟恢复默认。"""
    init_db.reset_data()
    config.SIMULATE_DB_LATENCY = 0.05
    yield
    config.SIMULATE_DB_LATENCY = 0.05


@pytest.fixture
def wide_race_window():
    """把「查车位」到「占车位」之间的延迟放大，让并发缺陷稳定复现。"""
    config.SIMULATE_DB_LATENCY = 0.3
    yield 0.3
    config.SIMULATE_DB_LATENCY = 0.05


# ==================================================================
#  直连数据库（做数据层反向校验用）
# ==================================================================
@pytest.fixture
def db():
    # 用元组游标：直连查库时按位置取字段更顺手
    conn = pymysql.connect(
        autocommit=True, cursorclass=pymysql.cursors.Cursor, **config.DB_CONFIG)
    yield conn
    conn.close()


def spot_status(db, spot_code):
    with db.cursor() as cur:
        cur.execute("SELECT status, plate FROM spots WHERE code = %s", (spot_code,))
        return cur.fetchone()


def spot_status_by_id(db, spot_id):
    with db.cursor() as cur:
        cur.execute("SELECT status, plate FROM spots WHERE id = %s", (spot_id,))
        return cur.fetchone()


def ticket_row(db, ticket_id):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, plate, spot_id, status, fee, duration_minutes "
            "FROM tickets WHERE id = %s", (ticket_id,))
        return cur.fetchone()


def count(db, sql, args=()):
    with db.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()[0]

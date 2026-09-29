# -*- coding: utf-8 -*-
"""冒烟检查：一条命令确认服务能跑通主链路。

    python tools/smoke_check.py

主链路：车位总览 -> 车辆入场 -> 查记录 -> 出场计费 -> 再查总览。
全部通过则退出码为 0。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sut import server as sut_server          # noqa: E402
from sut import service                       # noqa: E402
from tests.client import ApiClient            # noqa: E402

PLATE = "津A12345"


def show(label, resp):
    ok = "OK " if resp.status == 200 else "FAIL"
    body = str(resp.payload)
    print("%s %-22s HTTP %d  %s" % (ok, label, resp.status, body[:120]))
    return resp.status == 200


def main():
    httpd, base = sut_server.run_in_thread(port=0)
    print("服务已启动：%s\n" % base)
    print("-" * 68)

    api = ApiClient(base)
    all_ok = True

    all_ok &= show("健康检查", api.get("/health"))
    summary = api.get("/api/lot/summary")
    all_ok &= show("车位总览", summary)
    print("     总车位 %s / 空闲 %s" % (summary.data["total"], summary.data["free"]))

    all_ok &= show("车辆入场", api.post("/api/vehicles/entry", {"plate": PLATE}))

    service.advance_clock(3 * 3600)               # 模拟停车 3 小时
    all_ok &= show("停车 3 小时后出场", api.post("/api/vehicles/exit", {"plate": PLATE}))

    summary = api.get("/api/lot/summary")
    all_ok &= show("出场后车位总览", summary)
    print("     总车位 %s / 空闲 %s" % (summary.data["total"], summary.data["free"]))

    print("-" * 68)
    print("冒烟结果：%s" % ("全部通过" if all_ok else "存在失败项"))
    httpd.shutdown()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

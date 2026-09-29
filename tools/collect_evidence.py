# -*- coding: utf-8 -*-
"""取证脚本：把每个缺陷的「实际观测值」原样抓出来，供文档引用。

用法（在项目根目录）：
    python tools/collect_evidence.py
"""
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sut import server as sut_server          # noqa: E402
from sut import service                       # noqa: E402
from sut.store import store                   # noqa: E402
from tests.client import ApiClient            # noqa: E402

PLATE_A = "津A12345"
PLATE_B = "津B22222"
EXPIRED = "2020-01-01"


def fresh(base):
    store.reset()
    service.reset_clock()
    return ApiClient(base)


def main():
    httpd, base = sut_server.run_in_thread(port=0)
    out = []
    try:
        # ---------------- BUG-S1 计费取整 ----------------
        api = fresh(base)
        api.post("/api/vehicles/entry", {"plate": PLATE_A})
        service.advance_clock(61 * 60)
        fee61 = api.post("/api/vehicles/exit", {"plate": PLATE_A}).data["fee"]

        api = fresh(base)
        api.post("/api/vehicles/entry", {"plate": PLATE_A})
        service.advance_clock(150 * 60)
        fee150 = api.post("/api/vehicles/exit", {"plate": PLATE_A}).data["fee"]
        out.append(("BUG-S1",
                    "停车 61 分钟 -> 收费 %.1f 元（应为 8.0：首小时 5 + 1 小时 3）" % fee61,
                    "停车 150 分钟 -> 收费 %.1f 元（应为 11.0）" % fee150))

        # ---------------- BUG-S2 重复出场 ----------------
        api = fresh(base)
        api.post("/api/vehicles/entry", {"plate": PLATE_A})
        first = api.post("/api/vehicles/exit", {"plate": PLATE_A})
        second = api.post("/api/vehicles/exit", {"plate": PLATE_A})

        api = fresh(base)
        api.post("/api/vehicles/entry", {"plate": PLATE_A})
        api.post("/api/vehicles/exit", {"plate": PLATE_A})
        api.post("/api/vehicles/entry", {"plate": PLATE_B})       # B 停进刚空出的车位
        occupied_before = api.get("/api/lot/summary").data["occupied"]
        api.post("/api/vehicles/exit", {"plate": PLATE_A})        # A 再次出场
        occupied_after = api.get("/api/lot/summary").data["occupied"]
        parking = api.get("/api/tickets?status=PARKING").data["total"]
        out.append(("BUG-S2",
                    "第一次出场 HTTP=%d，第二次出场 HTTP=%d（应为 400）"
                    % (first.status, second.status),
                    "B 入场后占用车位=%d，A 重复出场后占用车位=%d" % (occupied_before, occupied_after),
                    "此时仍在场车辆数=%d（占用数与在场数不一致）" % parking))

        # ---------------- BUG-S3 并发入场 ----------------
        api = fresh(base)
        n = 12
        plates = ["津C%05d" % i for i in range(n)]
        results = []
        lock = threading.Lock()
        barrier = threading.Barrier(n)

        def do_entry(plate):
            barrier.wait()
            r = api.post("/api/vehicles/entry",
                         {"plate": plate, "spotType": "CHARGING"})
            with lock:
                results.append(r)

        ts = [threading.Thread(target=do_entry, args=(p,)) for p in plates]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

        ok = [r for r in results if r.status == 200]
        codes = sorted(set(r.data["spot_code"] for r in ok))
        out.append(("BUG-S3",
                    "充电车位总数=1，并发车辆=%d" % n,
                    "入场成功=%d 辆（应 <= 1）" % len(ok),
                    "被分配的车位号=%s" % (codes or "-")))

        # ---------------- BUG-S4 月卡有效期 ----------------
        api = fresh(base)
        api.post("/api/cards", {"plate": PLATE_A, "validUntil": EXPIRED})
        api.post("/api/vehicles/entry", {"plate": PLATE_A})
        service.advance_clock(3 * 3600)
        fee = api.post("/api/vehicles/exit", {"plate": PLATE_A}).data["fee"]
        out.append(("BUG-S4",
                    "月卡有效期=%s（已过期），停车 3 小时" % EXPIRED,
                    "实际收费 %.1f 元（应为 11.0）" % fee))
    finally:
        httpd.shutdown()

    print("=" * 72)
    for row in out:
        print(row[0])
        for line in row[1:]:
            print("   " + line)
        print("-" * 72)


if __name__ == "__main__":
    main()

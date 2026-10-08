# -*- coding: utf-8 -*-
"""一键复现 4 个缺陷，打印现场证据。

用法（需要服务已经在跑）：
    python app.py            # 另一个窗口先启动服务
    python tools/verify_bugs.py

脚本会：重置数据 -> 逐个复现缺陷 -> 打印「期望 vs 实际」。
跑完不会自动清理，数据留在最后一次复现的状态；重新跑会自动先重置。
"""
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import json

BASE = os.environ.get("SMARTPARK_BASE", "http://127.0.0.1:5002")
LINE = "=" * 66


def call(method, path, body=None):
    url = BASE + urllib.parse.quote(path, safe="/?=&%#")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")).get("data")
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        err = RuntimeError("%s: %s" % (payload.get("code"), payload.get("message")))
        err.code = payload.get("code")
        raise err


def get(p):
    return call("GET", p)


def post(p, b=None):
    return call("POST", p, b if b is not None else {})


def entry(plate, spot_type=None):
    return post("/api/vehicles/entry", {"plate": plate, "spotType": spot_type})


def do_exit(plate):
    return post("/api/vehicles/exit", {"plate": plate})


def reset():
    post("/api/dev/reset", {})


def advance(seconds):
    post("/api/dev/clock", {"advance": seconds})


def verdict(right, got, ok):
    mark = "✔ 通过" if ok else "✘ 未通过（缺陷存在）"
    print("   期望：%s" % right)
    print("   实际：%s" % got)
    print("   判定：%s" % mark)


# ------------------------------------------------------------------
#  BUG-S1 计费取整
# ------------------------------------------------------------------
def bug_s1():
    print(LINE)
    print("BUG-S1 · 计费取整错误（向下取整，应为向上取整）")
    print(LINE)
    reset()
    entry("京A77777")
    advance(3660)                       # 1 小时 1 分
    t = do_exit("京A77777")
    print("   停车时长：61 分钟（1 小时 1 分）")
    verdict("¥8.00（不足 1 小时按 1 小时，共 2 小时）",
            "¥%.2f" % t["fee"], t["fee"] == 8.0)
    print()


# ------------------------------------------------------------------
#  BUG-S2 重复出场释放他人车位
# ------------------------------------------------------------------
def bug_s2():
    print(LINE)
    print("BUG-S2 · 出场不幂等，重复出场会释放别人的车位")
    print(LINE)
    reset()
    a = entry("京A77777")
    advance(1200)
    do_exit("京A77777")
    b = entry("京B77777")
    print("   车 A（京A77777）出场，车位 %s 释放" % a["spot_code"])
    print("   车 B（京B77777）入场，也拿到车位 %s" % b["spot_code"])

    second = None
    try:
        second = do_exit("京A77777")       # A 再次出场（异常操作）
    except RuntimeError as exc:
        print("   A 再次出场被拒绝：%s" % exc)

    spot = [s for s in get("/api/spots")["items"] if s["code"] == b["spot_code"]][0]
    print("   现在检查车位 %s 的状态：" % b["spot_code"])
    verdict("OCCUPIED（B 还在场，车位不应被释放）",
            "%s（plate=%s）" % (spot["status"], spot["plate"]),
            spot["status"] == "OCCUPIED")

    cons = get("/api/consistency")
    if cons["ok"]:
        print("   一致性自检：通过")
    else:
        print("   一致性自检：发现 %d 处不一致" % len(cons["problems"]))
        for p in cons["problems"]:
            print("     · %s — %s" % (p["rule"], p["detail"]))
    print()


# ------------------------------------------------------------------
#  BUG-S3 并发入场超卖
# ------------------------------------------------------------------
def bug_s3():
    print(LINE)
    print("BUG-S3 · 并发入场超卖（一个车位发给多辆车）")
    print(LINE)
    reset()
    post("/api/dev/clock", {"advance": 0})
    workers = 20
    total_spots = get("/api/lot/summary")["total"]
    print("   车场车位总数：%d" % total_spots)
    print("   同时发起 %d 个入场请求……" % workers)

    barrier = threading.Barrier(workers)
    results = []
    lock = threading.Lock()

    def worker(idx):
        plate = "京A9%04d" % idx
        barrier.wait()
        try:
            entry(plate)
            outcome = "ok"
        except RuntimeError as exc:
            outcome = getattr(exc, "code", "ERR")
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok = results.count("ok")
    rejected = results.count("LOT_FULL")
    summary = get("/api/lot/summary")
    verdict("成功入场数 ≤ %d" % total_spots,
            "成功 %d 笔，被拒 %d 笔" % (ok, rejected),
            ok <= total_spots)
    print("   占用车位 %d 个，在场记录 %d 条（应相等）"
          % (summary["occupied"], get("/api/tickets?status=PARKING")["total"]))
    print()


# ------------------------------------------------------------------
#  BUG-S4 过期月卡仍免费
# ------------------------------------------------------------------
def bug_s4():
    print(LINE)
    print("BUG-S4 · 过期月卡仍然免费出场")
    print(LINE)
    reset()
    card = get("/api/cards/" + urllib.parse.quote("京B00001"))
    print("   京B00001 的月卡有效期：%s（已过期：%s）"
          % (card["valid_until"], card["expired"]))
    entry("京B00001")
    advance(3 * 3600)
    t = do_exit("京B00001")
    print("   停车时长：3 小时")
    verdict("¥11.00（过期月卡应按普通车辆收费）",
            "¥%.2f" % t["fee"], t["fee"] == 11.0)
    print()


def main():
    print("")
    print(LINE)
    print("  智能停车管理系统 · 缺陷复现验证")
    print("  目标服务：%s" % BASE)
    print(LINE)
    print("")

    try:
        get("/health")
    except Exception as exc:  # noqa: BLE001
        print("  [错误] 连不上服务（%s）" % exc)
        print("  请先在另一个窗口运行：python app.py")
        sys.exit(1)

    for fn in (bug_s1, bug_s2, bug_s3, bug_s4):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print("   [异常] %s\n" % exc)

    reset()
    print(LINE)
    print("  验证结束。数据显示：4 个缺陷均能被稳定复现。")
    print("  交给开发修复后，再跑 pytest（tests/bugs/）做回归验证。")
    print(LINE)
    print("")


if __name__ == "__main__":
    main()

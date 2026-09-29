# -*- coding: utf-8 -*-
"""缺陷复现 · 并发入场导致车位超发

BUG-S3 entry 中「查找空闲车位」与「占用车位」分两步执行，中间没有加锁，
        多个请求同时入场时会查到同一个空闲车位，导致一个车位被分配给多辆车
        —— 入场记录数远超车位数。
"""
import threading

import pytest

pytestmark = pytest.mark.known_bug

RACERS = 12          # 并发车辆数
PLATES = ["津A%05d" % i for i in range(RACERS)]


def _entry_concurrently(api, spot_type):
    """让 RACERS 辆车对齐后同时请求入场，返回所有响应。"""
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(RACERS)

    def do_entry(plate):
        barrier.wait()
        resp = api.post("/api/vehicles/entry",
                        {"plate": plate, "spotType": spot_type})
        with lock:
            results.append(resp)

    threads = [threading.Thread(target=do_entry, args=(p,)) for p in PLATES]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@pytest.mark.xfail(reason="BUG-S3 车位查找与占用非原子操作", strict=False)
def test_bug_s3_charging_spot_should_not_oversell(api):
    """BUG-S3 只有 1 个充电车位时，并发入场最多只能成功 1 辆。

    场景：充电车位仅 1 个，12 辆车同时请求充电车位。
    期望：最多 1 辆入场成功，其余返回 409（车位已满）
    实际：12 辆全部成功，且都拿到同一个车位 C-001
    """
    results = _entry_concurrently(api, "CHARGING")

    succeeded = [r for r in results if r.status == 200]
    assert len(succeeded) <= 1, \
        "充电车位只有 1 个，却成功入场 %d 辆" % len(succeeded)


@pytest.mark.xfail(reason="BUG-S3 同一车位被分配给多辆车", strict=False)
def test_bug_s3_one_spot_should_not_be_shared(api):
    """BUG-S3 同一个车位不应被分配给多辆车。

    期望：成功入场的车辆占用的车位互不相同
    实际：多辆车拿到同一个 spot_code
    """
    results = _entry_concurrently(api, "CHARGING")
    succeeded = [r for r in results if r.status == 200]

    codes = [r.data["spot_code"] for r in succeeded]
    assert len(set(codes)) == len(codes), \
        "同一车位 %s 被分配给了 %d 辆车" % (codes[0] if codes else "-", len(codes))


@pytest.mark.xfail(reason="BUG-S3 在场记录数超过车位总数", strict=False)
def test_bug_s3_parking_count_should_not_exceed_capacity(api):
    """BUG-S3 在场车辆数不应超过车位数。

    场景：全部 7 个车位，10 辆车同时入场。
    期望：在场记录 ≤ 7
    实际：超过 7 条
    """
    plates = ["津B%05d" % i for i in range(10)]
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(len(plates))

    def do_entry(plate):
        barrier.wait()
        resp = api.post("/api/vehicles/entry", {"plate": plate})
        with lock:
            results.append(resp)

    threads = [threading.Thread(target=do_entry, args=(p,)) for p in plates]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    parking = api.get("/api/tickets?status=PARKING").data["total"]
    assert parking <= 7, "车位总数 7，在场车辆却有 %d 辆" % parking

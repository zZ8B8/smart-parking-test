# -*- coding: utf-8 -*-
"""BUG-S3 · 并发入场超卖（一个车位发给多辆车）

需求：任意数量的并发入场请求，成功数不得超过空闲车位数，且
「占用车位数」必须始终等于「在场记录数」。

实际：service.entry() 把「查空闲车位」和「占用车位」拆成了两次无保护的数据库操作。
并发请求在两次操作之间的窗口里查到**同一个**空闲车位，
于是同一车位被分配给多辆车 —— 车位超卖。

复现要点：
    · 用 threading.Barrier 让所有请求在同一时刻起跑；
    · 用 wide_race_window 夹具把「查车位 → 占车位」的延迟放大到 0.3 秒，
      保证所有请求都在写入之前完成查询（真实系统中这段时间来自网络与调度）。
"""
import threading

import pytest

from tests.client import ApiError

WORKERS = 20          # 20 辆车同时冲进来
TOTAL_SPOTS = 7       # 车场只有 7 个车位


def _fire_entry_concurrently(api, workers=WORKERS):
    """让 workers 个线程同时入场，返回 [(结果, 车牌), ...]。"""
    barrier = threading.Barrier(workers)
    results = []
    lock = threading.Lock()

    def worker(idx):
        plate = "京A9%04d" % idx      # 京A90000 / 京A90001 ...
        barrier.wait()                # 等一下，大家一起冲
        try:
            api.entry(plate)
            outcome = "ok"
        except ApiError as exc:
            outcome = exc.code
        with lock:
            results.append((outcome, plate))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@pytest.mark.xfail(reason="BUG-S3 并发入场：查车位与占车位非原子，一个车位发给多辆车", strict=True)
def test_concurrent_entry_should_not_overbook(api, wide_race_window):
    """20 辆车同时入场，最多只能成功 7 辆（车位数）。"""
    results = _fire_entry_concurrently(api)
    ok = [r for r in results if r[0] == "ok"]
    assert len(ok) <= TOTAL_SPOTS, (
        "车场只有 %d 个车位，却有 %d 辆车入场成功" % (TOTAL_SPOTS, len(ok)))


@pytest.mark.xfail(reason="BUG-S3 并发入场导致占用车位数与在场记录数不一致", strict=True)
def test_concurrent_entry_should_keep_counts_equal(api, wide_race_window):
    """并发入场后，占用车位数必须等于在场记录数。"""
    _fire_entry_concurrently(api)
    assert api.occupied_spot_count() == api.open_ticket_count()


@pytest.mark.xfail(reason="BUG-S3 并发入场后车场数据自洽性被破坏", strict=True)
def test_concurrent_entry_should_stay_consistent(api, wide_race_window):
    """并发入场后，一致性自检应当通过。"""
    _fire_entry_concurrently(api)
    d = api.consistency()
    assert d["ok"] is True, d["problems"]


def test_sequential_entries_respect_capacity(api):
    """对照用例：**串行**入场时容量控制是正确的 —— 第 8 辆会被拒绝。

    这条不加 xfail，用来证明缺陷是「并发」引入的，
    而不是容量判断逻辑本身写错了。做缺陷定位时这种对照很有用。
    """
    for i in range(TOTAL_SPOTS):
        api.entry("京A8%04d" % i)

    with pytest.raises(ApiError) as err:
        api.entry("京A89999")
    assert err.value.code == "LOT_FULL"
    assert api.occupied_spot_count() == TOTAL_SPOTS
    assert api.consistency()["ok"] is True

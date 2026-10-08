# -*- coding: utf-8 -*-
"""BUG-S1 · 计费取整错误（向下取整，应为向上取整）

需求：「首小时 5 元，此后每满 1 小时 3 元（**不足 1 小时按 1 小时**）」。
「不足 1 小时按 1 小时」意味着小时数应向上取整（ceil），
但 service.calc_fee() 用的是向下取整（//），
导致超出整小时的那部分尾数被抹掉 —— 少收钱。

计算验证（首小时 5 元，之后每小时 3 元）：
    停车时长      正确小时数(ceil)   应收      实际小时数(floor)   实收
    1 小时 1 分        2             8 元          1              5 元   ← 少收 3
    2 小时 30 分       3            11 元          2              8 元   ← 少收 3
    5 小时 59 分       6            20 元          5             17 元   ← 少收 3

注：为避免时间精度带来的偶发失败，下面的用例都用「偏移量 + 零头」明确落在
某个非整数小时区间内，不卡在整点边界上。
"""
import pytest


@pytest.mark.xfail(reason="BUG-S1 计费向下取整：61 分钟只按 1 小时收费，应收 2 小时", strict=True)
def test_61_minutes_should_charge_two_hours(api):
    """停车 1 小时 1 分（3660 秒）应收 5 + 3 = 8 元，实际只收 5 元。"""
    api.entry("京A77777")
    api.advance_clock(3660)
    assert api.exit("京A77777")["fee"] == 8.0


@pytest.mark.xfail(reason="BUG-S1 计费向下取整：2 小时 30 分只按 2 小时收费，应收 3 小时", strict=True)
def test_2h30m_should_charge_three_hours(api):
    """停车 2 小时 30 分（9000 秒）应收 5 + 3*2 = 11 元，实际只收 8 元。"""
    api.entry("京A77777")
    api.advance_clock(9000)
    assert api.exit("京A77777")["fee"] == 11.0


@pytest.mark.xfail(reason="BUG-S1 计费向下取整：5 小时 59 分只按 5 小时收费，应收 6 小时", strict=True)
def test_5h59m_should_charge_six_hours(api):
    """停车 5 小时 59 分（21540 秒）应收 5 + 3*5 = 20 元，实际只收 17 元。"""
    api.entry("京A77777")
    api.advance_clock(21540)
    assert api.exit("京A77777")["fee"] == 20.0


def test_whole_hours_are_correct(api):
    """对照用例：停在整小时上时，取整方式不影响结果，两种算法一致。

    这条**不加 xfail**，用来证明缺陷只在「有零头」时出现，
    而不是整个计费都错 —— 缩小缺陷范围，避免误判。
    """
    api.entry("京A77777")
    api.advance_clock(2 * 3600)
    assert api.exit("京A77777")["fee"] == 8.0


def test_within_free_window_is_zero(api):
    """对照用例：15 分钟免费规则本身是正确的。"""
    api.entry("京A77777")
    api.advance_clock(10 * 60)
    assert api.exit("京A77777")["fee"] == 0.0

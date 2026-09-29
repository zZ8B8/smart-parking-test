# -*- coding: utf-8 -*-
"""缺陷复现 · 计费取整错误

BUG-S1 calc_fee 用向下取整（int(seconds // 3600)）计算计费小时数，
        导致「超过整小时后的零头」被抹掉。
        规则要求「不足 1 小时按 1 小时」，正确做法是向上取整。
"""
import pytest

pytestmark = pytest.mark.known_bug


@pytest.mark.xfail(reason="BUG-S1 计费时长向下取整，零头被抹掉", strict=False)
def test_bug_s1_sixty_one_minutes_should_be_two_hours(park, leave, advance):
    """BUG-S1 停车 61 分钟应按 2 小时计费（5 + 3 = 8 元）。

    期望：8.0    实际：5.0（零头 1 分钟被向下取整抹掉）
    """
    park("津A12345")
    advance(61 * 60)
    fee = leave("津A12345").data["fee"]
    assert fee == 8.0, "61 分钟实际收费 %.1f 元，应为 8.0 元" % fee


@pytest.mark.xfail(reason="BUG-S1 计费时长向下取整，零头被抹掉", strict=False)
def test_bug_s1_ninety_minutes_should_be_two_hours(park, leave, advance):
    """BUG-S1 停车 90 分钟应按 2 小时计费（8 元）。

    期望：8.0    实际：5.0
    """
    park("津A12345")
    advance(90 * 60)
    fee = leave("津A12345").data["fee"]
    assert fee == 8.0, "90 分钟实际收费 %.1f 元，应为 8.0 元" % fee


@pytest.mark.xfail(reason="BUG-S1 计费时长向下取整，零头被抹掉", strict=False)
def test_bug_s1_two_and_half_hours_should_be_three_hours(park, leave, advance):
    """BUG-S1 停车 2 小时 30 分应按 3 小时计费（11 元）。

    期望：11.0   实际：8.0
    """
    park("津A12345")
    advance(150 * 60)
    fee = leave("津A12345").data["fee"]
    assert fee == 11.0, "150 分钟实际收费 %.1f 元，应为 11.0 元" % fee

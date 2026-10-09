# -*- coding: utf-8 -*-
"""BUG-S4 · 过期月卡仍然免费出场（已修复 · 转为回归用例）

需求：「月卡：**有效期内**免费，车牌与月卡绑定」。
过期月卡不应再享受免费待遇，应按普通车辆计费。

修复前：service._has_free_pass() 只判断月卡记录是否存在，
**没有比对 valid_until 与当前时间**。于是过期月卡永久免费 —— 车场持续漏收。

修复：valid_until >= 当天才免费（含到期当天）。
本文件三条用例已转正为回归守卫。

初始数据里已经准备好一张过期月卡：京B00001（有效期 2024-01-01）。
"""


def test_expired_card_should_be_charged(api):
    """京B00001 的月卡 2024-01-01 就过期了，停 3 小时应收费 11 元。"""
    api.entry("京B00001")
    api.advance_clock(3 * 3600)
    assert api.exit("京B00001")["fee"] == 11.0


def test_expired_card_should_not_be_free(api):
    """过期月卡的出场费用不能为 0。"""
    api.entry("京B00001")
    api.advance_clock(6 * 3600)
    assert api.exit("京B00001")["fee"] != 0.0


def test_expired_and_valid_card_behave_differently(api):
    """有效月卡（京A12345）免费，过期月卡（京B00001）应收费 —— 两者不应一样。"""
    api.entry("京A12345")
    api.entry("京B00001")
    api.advance_clock(3 * 3600)
    valid_fee = api.exit("京A12345")["fee"]
    expired_fee = api.exit("京B00001")["fee"]

    assert valid_fee == 0.0
    assert expired_fee > 0.0, "过期月卡不应免费"


def test_valid_card_is_free(api):
    """对照用例：有效期内月卡免费 —— 这部分逻辑是对的。"""
    api.entry("京A12345")
    api.advance_clock(3 * 3600)
    assert api.exit("京A12345")["fee"] == 0.0


def test_card_expiry_flag_is_reported(api):
    """对照用例：接口本身能正确算出「是否过期」，修复后计费也用了它。"""
    assert api.get_card("京B00001")["expired"] is True
    assert api.get_card("京A12345")["expired"] is False

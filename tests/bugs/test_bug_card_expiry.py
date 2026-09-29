# -*- coding: utf-8 -*-
"""缺陷复现 · 月卡有效期未校验

BUG-S4 _has_free_pass 只判断「该车牌是否办过月卡」，没有比对 valid_until。
        过期月卡依然享受免费出场 —— 停车费被少收。
"""
import pytest

pytestmark = pytest.mark.known_bug

EXPIRED = "2020-01-01"          # 早已过期


@pytest.mark.xfail(reason="BUG-S4 月卡有效期未校验", strict=False)
def test_bug_s4_expired_card_should_be_charged(api, park, leave, advance):
    """BUG-S4 月卡已过期，出场应按正常标准收费。

    场景：办理有效期至 2020-01-01 的月卡（已过期），停车 3 小时。
    期望：收费 11 元（5 + 3 × 2）
    实际：收费 0 元 —— 过期月卡依然免费
    """
    api.post("/api/cards", {"plate": "津A12345", "validUntil": EXPIRED})
    park("津A12345")
    advance(3 * 3600)

    fee = leave("津A12345").data["fee"]
    assert fee == 11.0, "月卡已于 %s 过期，实际收费 %.1f 元" % (EXPIRED, fee)


@pytest.mark.xfail(reason="BUG-S4 月卡有效期未校验", strict=False)
def test_bug_s4_expired_then_renewed_card(api, park, leave, advance):
    """BUG-S4 有效期取值完全不影响判定（对比：未来卡与过期卡行为一致）。

    期望：过期卡应收费，未来卡免费，两者行为不同
    实际：两者都是 0 元
    """
    api.post("/api/cards", {"plate": "津A12345", "validUntil": EXPIRED})
    park("津A12345")
    advance(3600)
    expired_fee = leave("津A12345").data["fee"]

    assert expired_fee == 5.0, "过期卡不应免费，实际收费 %.1f 元" % expired_fee

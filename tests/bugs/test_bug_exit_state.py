# -*- coding: utf-8 -*-
"""缺陷复现 · 出场接口缺少状态校验（幂等性 / 数据一致性）

BUG-S2 exit_vehicle 取该车牌的「最后一条记录」结算，没有校验它是否已经出场过。
        重复调用出场接口会：① 覆盖已结算的费用；② 再次释放车位 ——
        如果这期间车位已被别的车占用，就会把**别人正在用的车位**错误释放。
"""
import pytest

pytestmark = pytest.mark.known_bug


@pytest.mark.xfail(reason="BUG-S2 出场接口未校验记录状态", strict=False)
def test_bug_s2_second_exit_should_be_rejected(park, leave):
    """BUG-S2 同一辆车重复出场应被拒绝。

    期望：第二次出场返回 400（该车已不在场）
    实际：返回 200，重新结算并覆盖已结算的记录
    """
    park("津A12345")
    assert leave("津A12345").status == 200

    resp = leave("津A12345")
    assert resp.status == 400, "已出场的车辆竟能再次出场：%s" % resp.payload


@pytest.mark.xfail(reason="BUG-S2 重复出场会释放他人正在使用的车位", strict=False)
def test_bug_s2_second_exit_should_not_release_others_spot(api, park, leave):
    """BUG-S2 重复出场不应把别人正在使用的车位释放掉。

    场景：A 停车 → 出场（车位空出）→ B 停入该车位 → A 再次调用出场接口
    期望：A 的第二次出场被拒绝，B 的车位不受影响（占用数仍为 1）
    实际：车位被再次释放，B 还在场但占用数变成 0，车位状态与实际不符
    """
    park("津A12345")                                   # A 入场
    leave("津A12345")                                  # A 出场，车位空出
    park("津B22222")                                   # B 停进刚空出的车位
    assert api.get("/api/lot/summary").data["occupied"] == 1

    leave("津A12345")                                  # A 再次出场（A 早已不在场）

    data = api.get("/api/lot/summary").data
    assert data["occupied"] == 1, \
        "B 仍在场，占用车位却显示为 %d（车位被错误释放）" % data["occupied"]


@pytest.mark.xfail(reason="BUG-S2 重复出场会重新结算并覆盖费用", strict=False)
def test_bug_s2_second_exit_should_not_recount_fee(park, leave, advance):
    """BUG-S2 重复出场不应重新结算、覆盖已确定的费用。

    期望：首次出场时长为 1 小时 → 5 元，之后费用不再变化
    实际：再次出场时按「入场到现在」重新结算，费用被改写为 8 元
    """
    park("津A12345")
    advance(3600)
    first = leave("津A12345").data["fee"]
    assert first == 5.0

    advance(3600)
    second = leave("津A12345").data["fee"]
    assert second == 5.0, "已结算的订单被重新计费为 %.1f 元" % second

# -*- coding: utf-8 -*-
"""BUG-S2 · 出场接口不幂等，重复出场会释放别人的车位

需求：出场应当是一次性的状态流转 —— 记录从 PARKING 变成 CLOSED 之后，
再次调用出场接口应被拒绝（400），且不得再次释放车位。

实际：service.exit_vehicle() 取「该车牌最后一条记录」时，
没有校验它是否已经出场过，也不做幂等。后果有两层：

  1. 同一笔记录被反复「关闭」，重复写 EXIT 流水；
  2. 更严重的是：车位被释放后如果已经有**另一辆车**停了进去，
     重复出场会把**别人的车位**一起释放掉 ——
     车位表显示空闲，但对方还在场，车位可以再卖一次。

复现路径：
    车 A 入场 → A 出场（车位释放）→ 车 B 入场（拿到同一车位）→ A 再次出场
                                                        ↑ 这一步会把 B 的车位释放
"""
import pytest

from tests.client import ApiError
from tests.conftest import spot_status_by_id


@pytest.mark.xfail(reason="BUG-S2 出场不幂等：重复出场未被拒绝", strict=True)
def test_second_exit_should_be_rejected(api):
    """已经出场的记录再次出场，应返回 400，而不是再次成功。"""
    api.entry("京A77777")
    api.advance_clock(1200)
    api.exit("京A77777")

    with pytest.raises(ApiError) as err:
        api.exit("京A77777")
    assert err.value.status == 400


@pytest.mark.xfail(reason="BUG-S2 重复出场会把已停入的另一辆车的车位释放掉", strict=True)
def test_repeat_exit_should_not_free_others_spot(api, db):
    """A 出场后 B 停进同一车位，A 再次出场不能把 B 的车位释放。"""
    # 1) 车 A 入场再出场，车位释放
    a = api.entry("京A77777")
    api.advance_clock(1200)
    api.exit("京A77777")

    # 2) 车 B 入场，拿到同一个车位
    b = api.entry("京B12345")
    assert b["spot_id"] == a["spot_id"]
    assert spot_status_by_id(db, b["spot_id"]) == ("OCCUPIED", "京B12345")

    # 3) 车 A 再次出场（异常操作）
    try:
        api.exit("京A77777")
    except ApiError:
        pass  # 正确实现会在这里报错，车位自然安全

    # 4) B 的车位必须仍被占用
    assert spot_status_by_id(db, b["spot_id"]) == ("OCCUPIED", "京B12345")


@pytest.mark.xfail(reason="BUG-S2 重复出场重复写 EXIT 流水，车位流水失衡", strict=True)
def test_repeat_exit_should_not_duplicate_spot_log(api, db):
    """重复出场不应产生第二条 EXIT 流水。"""
    api.entry("京A77777")
    api.advance_clock(1200)
    api.exit("京A77777")
    try:
        api.exit("京A77777")
    except ApiError:
        pass

    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM spot_logs WHERE action = 'EXIT'")
        n = cur.fetchone()[0]
    assert n == 1


@pytest.mark.xfail(reason="BUG-S2 重复出场导致占用车位数与在场记录数不再相等", strict=True)
def test_repeat_exit_should_keep_consistency(api):
    """重复出场之后，车场数据仍应自洽。"""
    api.entry("京A77777")
    api.advance_clock(1200)
    api.exit("京A77777")
    api.entry("京B12345")      # 另一辆车补位
    try:
        api.exit("京A77777")   # 异常重复出场
    except ApiError:
        pass

    assert api.consistency()["ok"] is True


def test_single_exit_works(api):
    """对照用例：正常出场一次是完全正确的。"""
    api.entry("京A77777")
    api.advance_clock(1200)
    t = api.exit("京A77777")
    assert t["status"] == "CLOSED"
    assert api.consistency()["ok"] is True

# -*- coding: utf-8 -*-
"""出场与计费模块 · 功能测试

计费规则（见 docs/接口文档.md）：
    15 分钟内免费；超过后首小时 5 元；此后每满 1 小时 3 元（不足 1 小时按 1 小时）；
    单日封顶 40 元。

本文件只覆盖**计费正确**的区间；把「不足 1 小时按 1 小时」执行错的部分
放在 tests/bugs/test_bug_billing.py 里单独跟踪。
"""
import pytest
from urllib.parse import quote

pytestmark = pytest.mark.functional


class TestExit(object):

    def test_exit_success(self, api, park, leave):
        """TC-EXIT-001 出场成功：记录关闭、返回费用"""
        park("津A12345")
        resp = leave("津A12345")
        assert resp.status == 200
        assert resp.data["status"] == "CLOSED"
        assert resp.data["exited_at"] is not None
        assert resp.data["fee"] is not None

    def test_exit_releases_spot(self, api, park, leave):
        """TC-EXIT-002 出场后车位被释放"""
        park("津A12345")
        assert api.get("/api/lot/summary").data["free"] == 6
        leave("津A12345")
        assert api.get("/api/lot/summary").data["free"] == 7

    def test_exit_frees_spot_for_others(self, api, park, leave):
        """TC-EXIT-003 释放出的车位可被下一辆车使用"""
        park("津A12345")
        assert api.get("/api/lot/summary").data["free"] == 6
        leave("津A12345")
        assert park("津B22222").status == 200
        assert api.get("/api/lot/summary").data["free"] == 6

    def test_exit_unknown_plate(self, api, leave):
        """TC-EXIT-004 未入场的车辆出场返回 404"""
        resp = leave("津A12345")
        assert resp.status == 404
        assert resp.code == "TICKET_NOT_FOUND"

    def test_exit_records_duration(self, api, park, leave, advance):
        """TC-EXIT-005 出场记录停车时长（分钟）"""
        park("津A12345")
        advance(2 * 3600 + 30 * 60)          # 150 分钟
        resp = leave("津A12345")
        assert resp.data["duration_minutes"] == 150


class TestBilling(object):
    """计费规则（只在「不触发取整缺陷」的区间上断言）"""

    def test_within_free_period(self, api, park, leave, advance):
        """TC-BILL-001 停车 15 分钟（含）以内免费 —— 边界值"""
        park("津A12345")
        advance(15 * 60)
        assert leave("津A12345").data["fee"] == 0.0

    def test_just_over_free_period(self, api, park, leave, advance):
        """TC-BILL-002 停车 15 分 1 秒即收费，按首小时计 —— 边界值"""
        park("津A12345")
        advance(15 * 60 + 1)
        assert leave("津A12345").data["fee"] == 5.0

    def test_half_hour(self, api, park, leave, advance):
        """TC-BILL-003 停车 30 分钟按首小时 5 元"""
        park("津A12345")
        advance(30 * 60)
        assert leave("津A12345").data["fee"] == 5.0

    def test_exactly_one_hour(self, api, park, leave, advance):
        """TC-BILL-004 停车恰好 1 小时 5 元 —— 边界值"""
        park("津A12345")
        advance(3600)
        assert leave("津A12345").data["fee"] == 5.0

    def test_exactly_two_hours(self, api, park, leave, advance):
        """TC-BILL-005 停车恰好 2 小时 8 元（5 + 3） —— 边界值"""
        park("津A12345")
        advance(2 * 3600)
        assert leave("津A12345").data["fee"] == 8.0

    def test_exactly_three_hours(self, api, park, leave, advance):
        """TC-BILL-006 停车恰好 3 小时 11 元（5 + 3 × 2）"""
        park("津A12345")
        advance(3 * 3600)
        assert leave("津A12345").data["fee"] == 11.0

    def test_daily_cap(self, api, park, leave, advance):
        """TC-BILL-007 停车 24 小时触发单日封顶 40 元 —— 边界值"""
        park("津A12345")
        advance(24 * 3600)
        assert leave("津A12345").data["fee"] == 40.0

    def test_cap_not_reached(self, api, park, leave, advance):
        """TC-BILL-008 停车 12 小时未到封顶（5 + 3 × 11 = 38）"""
        park("津A12345")
        advance(12 * 3600)
        assert leave("津A12345").data["fee"] == 38.0


class TestTicketQuery(object):

    def test_list_tickets_by_plate(self, api, park, leave):
        """TC-EXIT-006 按车牌查记录，两次停车共 2 条"""
        park("津A12345")
        leave("津A12345")
        park("津A12345")
        data = api.get("/api/tickets?plate=%s" % quote("津A12345")).data
        assert data["total"] == 2

    def test_filter_by_status(self, api, park):
        """TC-EXIT-007 按状态筛选在场记录"""
        park("津A12345")
        park("津B22222")
        data = api.get("/api/tickets?status=PARKING").data
        assert data["total"] == 2
        assert api.get("/api/tickets?status=CLOSED").data["total"] == 0

    def test_ticket_detail(self, api, park):
        """TC-EXIT-008 查询记录详情"""
        tid = park("津A12345").data["id"]
        resp = api.get("/api/tickets/%s" % tid)
        assert resp.status == 200
        assert resp.data["plate"] == "津A12345"

    def test_ticket_not_found(self, api):
        """TC-EXIT-009 记录不存在返回 404"""
        resp = api.get("/api/tickets/TK99999")
        assert resp.status == 404
        assert resp.code == "TICKET_NOT_FOUND"

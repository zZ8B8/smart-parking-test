# -*- coding: utf-8 -*-
"""车位模块 · 功能测试

用例编号与 docs/测试用例.md 一一对应。
"""
import pytest

pytestmark = pytest.mark.functional


class TestLotSummary(object):
    """车位总览"""

    def test_summary_initial(self, api):
        """TC-LOT-001 初始车位总览：总数 7，全部空闲"""
        data = api.get("/api/lot/summary").data
        assert data["total"] == 7
        assert data["free"] == 7
        assert data["occupied"] == 0

    def test_summary_by_type(self, api):
        """TC-LOT-002 按类型统计正确（4 普通 / 2 无障碍 / 1 充电）"""
        by_type = api.get("/api/lot/summary").data["byType"]
        assert by_type["NORMAL"]["total"] == 4
        assert by_type["ACCESSIBLE"]["total"] == 2
        assert by_type["CHARGING"]["total"] == 1

    def test_summary_after_park(self, api, park):
        """TC-LOT-003 一辆车入场后空闲数减 1、占用数加 1"""
        park("津A12345")
        data = api.get("/api/lot/summary").data
        assert data["free"] == 6
        assert data["occupied"] == 1

    def test_summary_after_leave(self, api, park, leave):
        """TC-LOT-004 车辆出场后空闲数恢复"""
        park("津A12345")
        leave("津A12345")
        data = api.get("/api/lot/summary").data
        assert data["free"] == 7
        assert data["occupied"] == 0


class TestSpotList(object):
    """车位列表"""

    def test_list_all(self, api):
        """TC-LOT-005 车位列表按编号升序返回 7 条"""
        data = api.get("/api/spots").data
        assert data["total"] == 7
        codes = [s["code"] for s in data["items"]]
        assert codes == sorted(codes)

    def test_filter_by_status(self, api, park):
        """TC-LOT-006 按状态筛选：占用 1 条、空闲 6 条"""
        park("津A12345")
        assert api.get("/api/spots?status=OCCUPIED").data["total"] == 1
        assert api.get("/api/spots?status=FREE").data["total"] == 6

    def test_filter_by_type(self, api):
        """TC-LOT-007 按类型筛选：充电车位只有 1 个"""
        data = api.get("/api/spots?type=CHARGING").data
        assert data["total"] == 1
        assert data["items"][0]["code"].startswith("C-")

    def test_occupied_spot_records_plate(self, api, park):
        """TC-LOT-008 被占用车位记录对应车牌"""
        park("津A12345")
        occupied = api.get("/api/spots?status=OCCUPIED").data["items"][0]
        assert occupied["plate"] == "津A12345"

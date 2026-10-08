# -*- coding: utf-8 -*-
"""车位模块测试：车场总览、车位列表与筛选、数据一致性。"""
import pytest


class TestLotSummary:

    def test_initial_summary(self, api):
        """初始状态：7 个车位全部空闲。"""
        d = api.summary()
        assert d["total"] == 7
        assert d["free"] == 7
        assert d["occupied"] == 0

    def test_by_type_total(self, api):
        """按类型统计的总数应覆盖全部 7 个车位。"""
        d = api.summary()
        assert d["byType"]["NORMAL"]["total"] == 4
        assert d["byType"]["ACCESSIBLE"]["total"] == 2
        assert d["byType"]["CHARGING"]["total"] == 1
        total = sum(v["total"] for v in d["byType"].values())
        assert total == d["total"]

    def test_summary_after_entry(self, api):
        """停一辆车后，占用数 +1、空闲数 -1。"""
        api.entry("京A10001")
        d = api.summary()
        assert d["occupied"] == 1
        assert d["free"] == 6

    def test_by_type_free_decreases(self, api):
        """停进充电车位后，充电车位的空闲数应为 0。"""
        api.entry("京A10002", spot_type="CHARGING")
        d = api.summary()
        assert d["byType"]["CHARGING"]["free"] == 0
        assert d["byType"]["CHARGING"]["occupied"] == 1
        assert d["byType"]["NORMAL"]["free"] == 4


class TestSpotList:

    def test_list_all(self, api):
        d = api.spots()
        assert d["total"] == 7
        codes = [s["code"] for s in d["items"]]
        assert codes == sorted(codes), "车位应按编号升序"

    def test_filter_free(self, api):
        assert api.spots(status="FREE")["total"] == 7
        assert api.spots(status="OCCUPIED")["total"] == 0

    def test_filter_by_type(self, api):
        d = api.spots(spot_type="CHARGING")
        assert d["total"] == 1
        assert d["items"][0]["code"] == "C-001"
        assert d["items"][0]["type"] == "CHARGING"

    @pytest.mark.parametrize("spot_type,expected", [
        ("NORMAL", 4), ("ACCESSIBLE", 2), ("CHARGING", 1),
    ])
    def test_type_counts(self, api, spot_type, expected):
        assert api.spots(spot_type=spot_type)["total"] == expected

    def test_occupied_spot_records_plate(self, api):
        api.entry("京A10003")
        occupied = api.spots(status="OCCUPIED")["items"]
        assert len(occupied) == 1
        assert occupied[0]["plate"] == "京A10003"


class TestConsistency:

    def test_initial_consistent(self, api):
        d = api.consistency()
        assert d["ok"] is True, d["problems"]

    def test_consistent_after_entry_and_exit(self, api):
        """正常的进出场之后，数据仍应自洽。"""
        api.advance_clock(3600)
        api.entry("京A10004")
        assert api.consistency()["ok"] is True
        api.exit("京A10004")
        assert api.consistency()["ok"] is True

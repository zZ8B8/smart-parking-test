# -*- coding: utf-8 -*-
"""入场模块 · 功能测试"""
import pytest

pytestmark = pytest.mark.functional


class TestEntry(object):

    def test_entry_success(self, api, park):
        """TC-ENTRY-001 正常入场：生成在场记录并占用车位"""
        resp = park("津A12345")
        assert resp.status == 200
        assert resp.data["plate"] == "津A12345"
        assert resp.data["status"] == "PARKING"
        assert resp.data["exited_at"] is None
        assert resp.data["fee"] is None

    def test_entry_by_spot_type(self, api, park):
        """TC-ENTRY-002 指定车位类型入场，分配到对应类型车位"""
        resp = park("津A12345", spot_type="CHARGING")
        assert resp.status == 200
        assert resp.data["spot_code"].startswith("C-")

    def test_entry_same_plate_twice(self, api, park):
        """TC-ENTRY-003 同一车牌连续入场被拒绝"""
        assert park("津A12345").status == 200
        resp = park("津A12345")
        assert resp.status == 400
        assert resp.code == "ALREADY_PARKED"

    def test_entry_after_leave_allowed(self, api, park, leave):
        """TC-ENTRY-004 出场后同一车牌可再次入场"""
        park("津A12345")
        leave("津A12345")
        assert park("津A12345").status == 200

    @pytest.mark.parametrize("plate", [
        "",            # 空
        "A12345",      # 缺省份简称
        "津12A45",     # 第二位不是字母
        "津A123",      # 位数不足
        "津A12345678",  # 位数过多
    ])
    def test_entry_invalid_plate(self, api, park, plate):
        """TC-ENTRY-005 车牌格式非法被拒绝（等价类 / 边界值：5 组）"""
        resp = park(plate)
        assert resp.status == 400
        assert resp.code == "INVALID_PLATE"

    def test_entry_new_energy_plate(self, api, park):
        """TC-ENTRY-006 新能源 8 位车牌可以正常入场"""
        assert park("津AD12345").status == 200

    def test_entry_lot_full(self, api, park):
        """TC-ENTRY-007 车位耗尽时拒绝入场（边界值：7 个车位正好停满）"""
        for i in range(7):
            assert park("津A0000%d" % i).status == 200
        assert api.get("/api/lot/summary").data["free"] == 0

        resp = park("津A99999")
        assert resp.status == 409
        assert resp.code == "LOT_FULL"

    def test_entry_charging_lot_full(self, api, park):
        """TC-ENTRY-008 指定类型车位耗尽时拒绝入场（充电位只有 1 个）"""
        assert park("津A11111", spot_type="CHARGING").status == 200
        resp = park("津A22222", spot_type="CHARGING")
        assert resp.status == 409
        assert resp.code == "LOT_FULL"

    def test_entry_creates_one_ticket_per_vehicle(self, api, park):
        """TC-ENTRY-009 入场生成 1 条记录，车位占用数同步为 1"""
        park("津A12345")
        tickets = api.get("/api/tickets").data
        assert tickets["total"] == 1
        assert api.get("/api/lot/summary").data["occupied"] == 1

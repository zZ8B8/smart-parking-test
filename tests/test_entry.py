# -*- coding: utf-8 -*-
"""入场模块测试：车牌校验、车位分配、重复入场、车位耗尽。"""
import pytest

from tests.client import ApiError
from tests.conftest import spot_status_by_id


PLATE_INVALID = ["", "   ", "ABC12345", "京12345", "京A123", "京A12345678", "京A-1234"]


class TestEntrySuccess:

    def test_entry_returns_ticket(self, api):
        t = api.entry("京A12345")
        assert t["plate"] == "京A12345"
        assert t["status"] == "PARKING"
        assert t["spot_code"]
        assert t["entered_at"]
        assert t["exited_at"] is None

    def test_entry_occupies_spot(self, api, db):
        t = api.entry("京A12345")
        assert api.occupied_spot_count() == 1
        assert api.free_spot_count() == 6
        assert spot_status_by_id(db, t["spot_id"]) == ("OCCUPIED", "京A12345")

    def test_entry_picks_smallest_code_first(self, api):
        """空闲车位按编号升序分配，第一个应是 A-001。"""
        t = api.entry("京A12345")
        assert t["spot_code"] == "A-001"

    def test_second_entry_uses_next_spot(self, api):
        api.entry("京A12345")
        t2 = api.entry("京A12346")
        assert t2["spot_code"] == "A-002"

    def test_specific_spot_type(self, api):
        t = api.entry("京A12345", spot_type="CHARGING")
        assert t["spot_code"] == "C-001"
        assert t["spot_type"] == "CHARGING"

    def test_accessible_spot_type(self, api):
        t = api.entry("京A12345", spot_type="ACCESSIBLE")
        assert t["spot_code"] in ("B-001", "B-002")

    def test_entry_writes_spot_log(self, api, db):
        api.entry("京A12345")
        with db.cursor() as cur:
            cur.execute("SELECT action, plate FROM spot_logs")
            rows = cur.fetchall()
        assert list(rows) == [("ENTRY", "京A12345")]

    def test_exit_then_entry_again(self, api):
        """同一车牌出场后可以再次入场。"""
        api.entry("京A12345")
        api.advance_clock(600)
        api.exit("京A12345")
        t = api.entry("京A12345")
        assert t["status"] == "PARKING"


class TestPlateValidation:

    @pytest.mark.parametrize("plate", PLATE_INVALID)
    def test_invalid_plate_rejected(self, api, plate):
        with pytest.raises(ApiError) as err:
            api.entry(plate)
        assert err.value.status == 400
        assert err.value.code == "INVALID_PLATE"

    @pytest.mark.parametrize("plate", [
        "京A12345", "粤B8888E", "沪C00001", "京A123456", "苏E1234Z",
    ])
    def test_valid_plate_accepted(self, api, plate):
        t = api.entry(plate)
        assert t["plate"] == plate

    def test_missing_plate(self, api):
        with pytest.raises(ApiError) as err:
            api.post("/api/vehicles/entry", {})
        assert err.value.code == "INVALID_PLATE"


class TestEntryConflicts:

    def test_duplicate_entry_rejected(self, api):
        """同一车牌在场时不能再次入场。"""
        api.entry("京A12345")
        with pytest.raises(ApiError) as err:
            api.entry("京A12345")
        assert err.value.status == 409
        assert err.value.code == "ALREADY_PARKED"
        assert api.occupied_spot_count() == 1

    def test_duplicate_entry_does_not_create_ticket(self, api):
        api.entry("京A12345")
        with pytest.raises(ApiError):
            api.entry("京A12345")
        assert api.open_ticket_count() == 1

    def test_lot_full_rejected(self, api):
        """7 个车位停满后，第 8 辆车应被拒绝。"""
        for i in range(7):
            api.entry("京A200%02d" % i)
        assert api.free_spot_count() == 0

        with pytest.raises(ApiError) as err:
            api.entry("京A30001")
        assert err.value.status == 409
        assert err.value.code == "LOT_FULL"

    def test_lot_full_leaves_data_consistent(self, api):
        for i in range(7):
            api.entry("京A200%02d" % i)
        with pytest.raises(ApiError):
            api.entry("京A30001")
        assert api.consistency()["ok"] is True
        assert api.open_ticket_count() == 7

    def test_charging_full_even_if_normal_free(self, api):
        """充电车位只有 1 个，被占后即使普通车位还有空也拒绝。"""
        api.entry("京A12345", spot_type="CHARGING")
        assert api.free_spot_count() == 6
        with pytest.raises(ApiError) as err:
            api.entry("京A12346", spot_type="CHARGING")
        assert err.value.code == "LOT_FULL"

    def test_after_full_exit_allows_entry(self, api):
        for i in range(7):
            api.entry("京A200%02d" % i)
        api.advance_clock(600)
        api.exit("京A20000")
        t = api.entry("京A30001")
        assert t["status"] == "PARKING"


class TestTicketQuery:

    def test_ticket_detail(self, api):
        created = api.entry("京A12345")
        t = api.ticket(created["id"])
        assert t["id"] == created["id"]
        assert t["plate"] == "京A12345"

    def test_ticket_not_found(self, api):
        with pytest.raises(ApiError) as err:
            api.ticket(99999)
        assert err.value.status == 404
        assert err.value.code == "TICKET_NOT_FOUND"

    def test_filter_by_plate(self, api):
        api.entry("京A12345")
        api.entry("京B12345")
        d = api.tickets(plate="京A12345")
        assert d["total"] == 1
        assert d["items"][0]["plate"] == "京A12345"

    def test_filter_by_status(self, api):
        api.entry("京A12345")
        assert api.tickets(status="PARKING")["total"] == 1
        assert api.tickets(status="CLOSED")["total"] == 0

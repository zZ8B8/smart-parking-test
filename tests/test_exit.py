# -*- coding: utf-8 -*-
"""出场模块测试：计费规则、车位释放、状态流转、异常场景。

关于时间的稳定性：
    业务层取时间走的是「系统时间 + 时钟偏移」，而出场时长是
    「出场时间 - 入场时间」两个时间点之差（入场时间按秒截断存储）。
    因此实际算出的秒数会是「偏移量 + 不到 2 秒的零头」。
    为了避免用例卡在计费档位的临界点上产生偶发失败，
    下面的用例都取明确落在某个档位中间的值，不测「正好第 3600 秒」这类边界。
    边界值另有专项用例。
"""
import pytest

from tests.client import ApiError
from tests.conftest import spot_status_by_id


class TestExitSuccess:

    def test_exit_releases_spot(self, api):
        t = api.entry("京A77777")
        api.advance_clock(1200)
        api.exit("京A77777")
        assert api.free_spot_count() == 7
        assert api.occupied_spot_count() == 0
        assert api.ticket(t["id"])["status"] == "CLOSED"

    def test_exit_fills_times_and_duration(self, api):
        api.entry("京A77777")
        api.advance_clock(1200)
        t = api.exit("京A77777")
        assert t["exited_at"] is not None
        assert 20 <= t["duration_minutes"] <= 21
        assert t["fee"] == 5.0

    def test_exit_writes_spot_log(self, api, db):
        api.entry("京A77777")
        api.advance_clock(1200)
        api.exit("京A77777")
        with db.cursor() as cur:
            cur.execute("SELECT action FROM spot_logs ORDER BY id")
            rows = [r[0] for r in cur.fetchall()]
        assert rows == ["ENTRY", "EXIT"]

    def test_spot_reusable_after_exit(self, api):
        first = api.entry("京A77777")
        api.advance_clock(1200)
        api.exit("京A77777")
        second = api.entry("京B12345")
        assert second["spot_code"] == first["spot_code"]

    def test_exit_updates_spot_plate_to_null(self, api, db):
        t = api.entry("京A77777")
        api.advance_clock(1200)
        api.exit("京A77777")
        assert spot_status_by_id(db, t["spot_id"]) == ("FREE", None)

    def test_consistency_after_normal_flow(self, api):
        api.entry("京A77777")
        api.advance_clock(1200)
        api.exit("京A77777")
        assert api.consistency()["ok"] is True


class TestBilling:
    """计费规则：≤15 分钟免费；首小时 5 元；此后每满 1 小时 3 元；封顶 40 元。"""

    @pytest.mark.parametrize("minutes,expected", [
        (1, 0.0),        # 刚停一会儿
        (10, 0.0),       # 免费时长内
        (14, 0.0),       # 接近免费上限
    ])
    def test_free_within_15min(self, api, minutes, expected):
        api.entry("京A77777")
        api.advance_clock(minutes * 60)
        assert api.exit("京A77777")["fee"] == expected

    @pytest.mark.parametrize("hours,expected", [
        (1, 5.0),        # 首小时
        (2, 8.0),        # 5 + 3
        (3, 11.0),       # 5 + 3*2
        (4, 14.0),       # 5 + 3*3
        (6, 20.0),       # 5 + 3*5
    ])
    def test_hourly_fee(self, api, hours, expected):
        api.entry("京A77777")
        api.advance_clock(hours * 3600)
        assert api.exit("京A77777")["fee"] == expected

    def test_free_before_charged_after(self, api):
        """同一辆车：先停 10 分钟免费，再停 20 分钟收费。"""
        api.entry("京A77777")
        api.advance_clock(600)
        assert api.exit("京A77777")["fee"] == 0.0

        api.entry("京A77777")
        api.advance_clock(1200)
        assert api.exit("京A77777")["fee"] == 5.0

    def test_daily_cap(self, api):
        """13 小时应触发 40 元封顶（5 + 12*3 = 41 → 40）。"""
        api.entry("京A77777")
        api.advance_clock(13 * 3600)
        assert api.exit("京A77777")["fee"] == 40.0

    def test_fee_is_number_not_string(self, api):
        api.entry("京A77777")
        api.advance_clock(3600)
        assert isinstance(api.exit("京A77777")["fee"], float)


class TestExitExceptions:

    def test_exit_without_entry(self, api):
        with pytest.raises(ApiError) as err:
            api.exit("京A99999")
        assert err.value.status == 404
        assert err.value.code == "TICKET_NOT_FOUND"

    def test_exit_invalid_plate(self, api):
        with pytest.raises(ApiError) as err:
            api.exit("BADPLATE")
        assert err.value.status == 400
        assert err.value.code == "INVALID_PLATE"

    def test_exit_missing_plate(self, api):
        with pytest.raises(ApiError) as err:
            api.post("/api/vehicles/exit", {})
        assert err.value.code == "INVALID_PLATE"

    def test_exit_does_not_affect_other_vehicles(self, api):
        api.entry("京A11111")
        api.entry("京A22222")
        api.advance_clock(1200)
        api.exit("京A11111")
        assert api.open_ticket_count() == 1
        assert api.occupied_spot_count() == 1

    def test_entry_after_exit_same_plate(self, api):
        api.entry("京A77777")
        api.advance_clock(1200)
        api.exit("京A77777")
        t = api.entry("京A77777")
        assert t["status"] == "PARKING"
        assert api.open_ticket_count() == 1


class TestMonthlyCardFree:
    """有效月卡出场免费（正向用例）。"""

    def test_valid_card_is_free(self, api):
        """京A12345 的月卡有效期 2027-12-31，仍在有效期内。"""
        api.entry("京A12345")
        api.advance_clock(3 * 3600)
        assert api.exit("京A12345")["fee"] == 0.0

    def test_no_card_is_charged(self, api):
        """没有月卡的车牌正常收费。"""
        api.entry("京A55555")
        api.advance_clock(3 * 3600)
        assert api.exit("京A55555")["fee"] == 11.0

    def test_new_card_makes_free(self, api):
        api.issue_card("京A66666", "2027-12-31")
        api.entry("京A66666")
        api.advance_clock(3 * 3600)
        assert api.exit("京A66666")["fee"] == 0.0

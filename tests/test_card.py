# -*- coding: utf-8 -*-
"""月卡模块测试：办理、续办、查询、有效期标识。"""
import pytest

from tests.client import ApiError


class TestCardQuery:

    def test_initial_cards(self, api):
        d = api.cards()
        assert d["total"] == 2
        plates = sorted(c["plate"] for c in d["items"])
        assert plates == sorted(["京A12345", "京B00001"])

    def test_valid_card_not_expired(self, api):
        c = api.get_card("京A12345")
        assert c["valid_until"] == "2027-12-31"
        assert c["expired"] is False

    def test_expired_card_flagged(self, api):
        """初始数据里的 京B00001 有效期 2024-01-01，应标记为已过期。"""
        c = api.get_card("京B00001")
        assert c["valid_until"] == "2024-01-01"
        assert c["expired"] is True

    def test_card_not_found(self, api):
        with pytest.raises(ApiError) as err:
            api.get_card("京Z99999")
        assert err.value.status == 404
        assert err.value.code == "CARD_NOT_FOUND"


class TestIssueCard:

    def test_issue_new_card(self, api):
        c = api.issue_card("京C11111", "2028-06-30")
        assert c["plate"] == "京C11111"
        assert c["valid_until"] == "2028-06-30"
        assert c["issued_at"]
        assert api.cards()["total"] == 3

    def test_issue_expired_card(self, api):
        c = api.issue_card("京C22222", "2020-01-01")
        assert c["expired"] is True

    def test_reissue_updates_same_card(self, api):
        """同一车牌再次办理应更新有效期，而不是新增一张。"""
        api.issue_card("京C33333", "2027-01-01")
        api.issue_card("京C33333", "2029-12-31")
        assert api.cards()["total"] == 3      # 原有 2 张 + 新增 1 张
        assert api.get_card("京C33333")["valid_until"] == "2029-12-31"

    def test_invalid_plate(self, api):
        with pytest.raises(ApiError) as err:
            api.issue_card("ABC123", "2027-12-31")
        assert err.value.code == "INVALID_PLATE"

    @pytest.mark.parametrize("bad_date", ["2027/12/31", "20271231", "2027-13-01", "abc", ""])
    def test_invalid_date(self, api, bad_date):
        with pytest.raises(ApiError) as err:
            api.issue_card("京C44444", bad_date)
        assert err.value.status == 400
        assert err.value.code == "INVALID_DATE"

    def test_missing_fields(self, api):
        with pytest.raises(ApiError):
            api.post("/api/cards", {"plate": "京C55555"})

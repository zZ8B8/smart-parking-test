# -*- coding: utf-8 -*-
"""月卡模块 · 功能测试"""
import pytest
from urllib.parse import quote

pytestmark = pytest.mark.functional

FUTURE = "2099-12-31"


class TestCard(object):

    def test_issue_card(self, api):
        """TC-CARD-001 办理月卡成功"""
        resp = api.post("/api/cards", {"plate": "津A12345", "validUntil": FUTURE})
        assert resp.status == 200
        assert resp.data["plate"] == "津A12345"
        assert resp.data["valid_until"] == FUTURE

    def test_get_card(self, api):
        """TC-CARD-002 查询月卡"""
        api.post("/api/cards", {"plate": "津A12345", "validUntil": FUTURE})
        resp = api.get("/api/cards/%s" % quote("津A12345"))
        assert resp.status == 200
        assert resp.data["valid_until"] == FUTURE

    def test_card_not_found(self, api):
        """TC-CARD-003 未办月卡的车牌查询返回 404"""
        resp = api.get("/api/cards/%s" % quote("津A12345"))
        assert resp.status == 404
        assert resp.code == "CARD_NOT_FOUND"

    @pytest.mark.parametrize("bad", ["2027/12/31", "2027-13-01", "明天", ""])
    def test_issue_card_invalid_date(self, api, bad):
        """TC-CARD-004 有效期格式非法被拒绝（等价类：4 组）"""
        resp = api.post("/api/cards", {"plate": "津A12345", "validUntil": bad})
        assert resp.status == 400
        assert resp.code == "INVALID_DATE"

    def test_issue_card_invalid_plate(self, api):
        """TC-CARD-005 车牌格式非法不能办卡"""
        resp = api.post("/api/cards", {"plate": "ABC", "validUntil": FUTURE})
        assert resp.status == 400
        assert resp.code == "INVALID_PLATE"

    def test_card_holder_pays_nothing(self, api, park, leave, advance):
        """TC-CARD-006 月卡车辆出场免费"""
        api.post("/api/cards", {"plate": "津A12345", "validUntil": FUTURE})
        park("津A12345")
        advance(3 * 3600)
        resp = leave("津A12345")
        assert resp.status == 200
        assert resp.data["fee"] == 0.0

    def test_non_card_holder_pays(self, api, park, leave, advance):
        """TC-CARD-007 非月卡车辆正常计费"""
        park("津A12345")
        advance(3 * 3600)
        assert leave("津A12345").data["fee"] == 11.0

    def test_card_only_for_bound_plate(self, api, park, leave, advance):
        """TC-CARD-008 月卡只对绑定车牌生效"""
        api.post("/api/cards", {"plate": "津A12345", "validUntil": FUTURE})
        park("津B22222")
        advance(3 * 3600)
        assert leave("津B22222").data["fee"] == 11.0

    def test_card_issued_after_entry_still_applies(self, api, park, leave, advance):
        """TC-CARD-009 入场后再办月卡，出场时同样免费"""
        park("津A12345")
        advance(3600)
        api.post("/api/cards", {"plate": "津A12345", "validUntil": FUTURE})
        assert leave("津A12345").data["fee"] == 0.0

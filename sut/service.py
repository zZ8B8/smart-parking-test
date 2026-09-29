# -*- coding: utf-8 -*-
"""智能停车管理系统 · 业务逻辑层

server.py 只做 HTTP 适配，所有业务规则集中在这里。

核心规则：
- 计费：15 分钟内免费；超过后首小时 5 元，此后每满 1 小时 3 元（不足 1 小时按 1 小时）；
  单日封顶 40 元；
- 月卡：有效期内免费，车牌与月卡绑定；
- 入场：自动分配一个空闲车位；车位耗尽时拒绝入场；
- 出场：结算费用并释放车位。
"""
import re
import time
from datetime import datetime, timedelta

from .store import (store, SPOT_FREE, SPOT_OCCUPIED,
                    TICKET_PARKING, TICKET_CLOSED)

# --------------------------------------------------------------------------
# 计费参数
# --------------------------------------------------------------------------
FREE_SECONDS = 15 * 60        # 免费时长 15 分钟
FIRST_HOUR_FEE = 5.0          # 首小时（不足 1 小时按 1 小时）
PER_HOUR_FEE = 3.0            # 之后每满 1 小时
DAILY_CAP = 40.0              # 单日封顶

# 模拟「查询空闲车位」与「占用车位」之间的持久层往返耗时。
# 真实系统里这两步是两条独立的 SQL，中间必然有网络 + 磁盘延迟；
# 入场接口正是在这段窗口里被并发请求穿插，才出现一个车位发给多辆车。
DB_ROUND_TRIP = 0.02

# 车牌：首位为省份简称，第二位为字母，其后 5~6 位字母数字（新能源牌 8 位）
PLATE_RE = re.compile(r"^[\u4e00-\u9fa5][A-Z][A-Z0-9]{5,6}$")


class BizError(Exception):
    """业务异常：带错误码与建议的 HTTP 状态码。"""

    def __init__(self, code, message, http_status=400):
        super(BizError, self).__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


# --------------------------------------------------------------------------
# 时钟（供测试拨快时间用）
# --------------------------------------------------------------------------
_clock_offset = {"seconds": 0}


def advance_clock(seconds):
    """把系统时钟整体前移若干秒。用于在测试中模拟「车停了 N 小时」。

    只影响本模块内的时间计算，不改动操作系统时间。
    """
    _clock_offset["seconds"] += seconds


def reset_clock():
    _clock_offset["seconds"] = 0


def _now():
    return datetime.now() + timedelta(seconds=_clock_offset["seconds"])


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# 车位
# --------------------------------------------------------------------------
def list_spots(status=None, spot_type=None):
    """车位列表，可按状态与类型筛选。"""
    rows = list(store.spots.values())
    if status:
        rows = [s for s in rows if s["status"] == status]
    if spot_type:
        rows = [s for s in rows if s["type"] == spot_type]
    rows.sort(key=lambda s: s["code"])
    return {"total": len(rows), "items": rows}


def lot_summary():
    """车位总览：总数 / 空闲 / 占用，并给出各类型明细。"""
    spots = list(store.spots.values())
    free = [s for s in spots if s["status"] == SPOT_FREE]
    occupied = [s for s in spots if s["status"] == SPOT_OCCUPIED]

    by_type = {}
    for spot in spots:
        bucket = by_type.setdefault(
            spot["type"], {"total": 0, "free": 0, "occupied": 0})
        bucket["total"] += 1
        if spot["status"] == SPOT_FREE:
            bucket["free"] += 1
        else:
            bucket["occupied"] += 1

    return {
        "total": len(spots),
        "free": len(free),
        "occupied": len(occupied),
        "byType": by_type,
    }


def _find_free_spot(spot_type=None):
    """找一个空闲车位。可指定车位类型。"""
    for spot in sorted(store.spots.values(), key=lambda s: s["code"]):
        if spot["status"] != SPOT_FREE:
            continue
        if spot_type and spot["type"] != spot_type:
            continue
        return spot
    return None


# --------------------------------------------------------------------------
# 停车记录
# --------------------------------------------------------------------------
def _open_ticket_of(plate):
    """该车牌当前在场的记录，没有则返回 None。"""
    for ticket in store.tickets.values():
        if ticket["plate"] == plate and ticket["status"] == TICKET_PARKING:
            return ticket
    return None


def _validate_plate(plate):
    if not plate or not PLATE_RE.match(plate):
        raise BizError("INVALID_PLATE", "车牌格式不正确：%s" % plate)


def entry(plate, spot_type=None):
    """车辆入场：校验车牌 -> 找空闲车位 -> 占用 -> 生成停车记录。"""
    _validate_plate(plate)

    if _open_ticket_of(plate):
        raise BizError("ALREADY_PARKED", "车辆已在场：%s" % plate)

    spot = _find_free_spot(spot_type)
    if spot is None:
        raise BizError("LOT_FULL", "暂无可用车位", 409)

    # 注意：从「查到车位」到「占用车位」是两步，中间没有加锁保护。
    # 并发请求会在这段窗口里查到同一个空闲车位，于是同一车位被分配给多辆车。
    time.sleep(DB_ROUND_TRIP)

    spot["status"] = SPOT_OCCUPIED
    spot["plate"] = plate

    tid = store.next_id("TK")
    entered = _now()
    store.tickets[tid] = {
        "id": tid,
        "plate": plate,
        "spot_id": spot["id"],
        "spot_code": spot["code"],
        "entered_at": _fmt(entered),
        "exited_at": None,
        "duration_minutes": None,
        "fee": None,
        "status": TICKET_PARKING,
    }
    return store.tickets[tid]


def get_ticket(ticket_id):
    ticket = store.tickets.get(ticket_id)
    if ticket is None:
        raise BizError("TICKET_NOT_FOUND", "停车记录不存在", 404)
    return ticket


def list_tickets(plate=None, status=None):
    """停车记录列表。"""
    rows = list(store.tickets.values())
    if plate:
        rows = [t for t in rows if t["plate"] == plate]
    if status:
        rows = [t for t in rows if t["status"] == status]
    rows.sort(key=lambda t: t["id"])
    return {"total": len(rows), "items": rows}


# --------------------------------------------------------------------------
# 计费
# --------------------------------------------------------------------------
def calc_fee(seconds):
    """按时长计算停车费。

    规则：15 分钟内免费；超过后首小时 5 元，
    此后每满 1 小时 3 元（不足 1 小时按 1 小时）；单日封顶 40 元。
    """
    if seconds <= FREE_SECONDS:
        return 0.0

    # 不足 1 小时按 1 小时计 —— 这里用的是向下取整，
    # 导致超时部分不足 1 小时时被抹掉（如 61 分钟只按 1 小时收）。
    hours = int(seconds // 3600)
    if hours < 1:
        hours = 1

    fee = FIRST_HOUR_FEE + (hours - 1) * PER_HOUR_FEE
    return min(fee, DAILY_CAP)


def _has_free_pass(plate):
    """该车牌是否持有月卡（可免费出场）。"""
    card = store.cards.get(plate)
    if card is None:
        return False
    # 只判断月卡是否存在，没有比对有效期 —— 过期月卡依然免费。
    return True


def exit_vehicle(plate):
    """车辆出场：结算费用 -> 关闭记录 -> 释放车位。"""
    _validate_plate(plate)

    tickets = [t for t in store.tickets.values() if t["plate"] == plate]
    if not tickets:
        raise BizError("TICKET_NOT_FOUND", "未找到该车辆的入场记录", 404)

    # 取该车牌最后一条记录 —— 没有校验它是否已经出场过。
    ticket = tickets[-1]

    entered = datetime.strptime(ticket["entered_at"], "%Y-%m-%d %H:%M:%S")
    exited = _now()
    seconds = int((exited - entered).total_seconds())
    if seconds < 0:
        seconds = 0

    fee = 0.0 if _has_free_pass(plate) else calc_fee(seconds)

    ticket["exited_at"] = _fmt(exited)
    ticket["duration_minutes"] = seconds // 60
    ticket["fee"] = fee
    ticket["status"] = TICKET_CLOSED

    # 释放车位 —— 重复调用出场接口会重复执行这一步，导致车位虚增。
    spot = store.spots[ticket["spot_id"]]
    spot["status"] = SPOT_FREE
    spot["plate"] = None

    return ticket


# --------------------------------------------------------------------------
# 月卡
# --------------------------------------------------------------------------
def issue_card(plate, valid_until):
    """办理/续办月卡。valid_until 形如 2027-12-31。"""
    _validate_plate(plate)
    try:
        datetime.strptime(valid_until, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise BizError("INVALID_DATE", "有效期格式应为 YYYY-MM-DD")

    store.cards[plate] = {
        "plate": plate,
        "valid_until": valid_until,
        "issued_at": _fmt(_now()),
    }
    return store.cards[plate]


def get_card(plate):
    card = store.cards.get(plate)
    if card is None:
        raise BizError("CARD_NOT_FOUND", "该车牌未办理月卡", 404)
    return card

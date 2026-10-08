# -*- coding: utf-8 -*-
"""智能停车管理系统 · 业务逻辑层

接口层（app.py）只负责解析请求、调用这里、返回 JSON。
所有业务规则集中在这个文件里。

核心规则：
- 计费：15 分钟内免费；超过后首小时 5 元，此后每满 1 小时 3 元
        （不足 1 小时按 1 小时）；单日封顶 40 元；
- 月卡：**有效期内**免费，车牌与月卡绑定；
- 入场：自动分配一个空闲车位；车位耗尽时拒绝入场；
- 出场：结算费用并释放车位。

⚠️ 本项目是「测试靶场」：下面标注了 4 处**刻意保留的缺陷**，
   它们在代码里没有任何特殊标记，需要靠测试用例去发现。
   缺陷清单见 docs/05-缺陷报告.md。
"""
import decimal
import re
from datetime import datetime, timedelta

import config
import db

# ------------------------------------------------------------------
# 枚举常量
# ------------------------------------------------------------------
SPOT_NORMAL     = "NORMAL"       # 普通车位
SPOT_ACCESSIBLE = "ACCESSIBLE"   # 无障碍车位
SPOT_CHARGING   = "CHARGING"     # 充电车位

SPOT_FREE     = "FREE"
SPOT_OCCUPIED = "OCCUPIED"

TICKET_PARKING = "PARKING"       # 在场
TICKET_CLOSED  = "CLOSED"        # 已出场

# 计费参数（源头在 config.py）
FREE_SECONDS   = config.FREE_SECONDS
FIRST_HOUR_FEE = config.FIRST_HOUR_FEE
PER_HOUR_FEE   = config.PER_HOUR_FEE
DAILY_CAP      = config.DAILY_CAP

# 车牌：首位为省份简称，第二位为字母，其后 5~6 位字母数字（新能源牌 8 位）
PLATE_RE = re.compile(r"^[\u4e00-\u9fa5][A-Z][A-Z0-9]{5,6}$")

DT_FMT = "%Y-%m-%d %H:%M:%S"


class ApiError(Exception):
    """业务异常：接口层捕获后转成统一的 JSON 错误响应。"""

    def __init__(self, code, message, http_status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


# ==================================================================
#  时钟（供测试「拨快时间」用）
# ==================================================================
# 为什么需要它：验证计费规则要模拟「车停了 3 小时」，
# 总不能真在测试里等 3 小时。所以维护一个全局偏移量，
# 业务层取时间一律走 _now()，测试通过接口把它前移即可。
_clock_offset = {"seconds": 0}


def advance_clock(seconds):
    """把系统时钟整体前移若干秒（累加）。"""
    _clock_offset["seconds"] += int(seconds)
    return _clock_offset["seconds"]


def reset_clock():
    _clock_offset["seconds"] = 0


def clock_state():
    return {
        "offsetSeconds": _clock_offset["seconds"],
        "virtualNow": _fmt(_now()),
    }


def _now():
    return datetime.now() + timedelta(seconds=_clock_offset["seconds"])


def _fmt(dt):
    return dt.strftime(DT_FMT)


def _money(value):
    if value is None:
        return None
    return float(value)


# ==================================================================
#  车位
# ==================================================================
def lot_summary():
    """车场总览：总数 / 空闲 / 占用，并给出各类型明细。"""
    total = db.fetch_one("SELECT COUNT(*) AS n FROM spots")["n"]
    free = db.fetch_one(
        "SELECT COUNT(*) AS n FROM spots WHERE status = %s", (SPOT_FREE,))["n"]
    rows = db.fetch_all(
        "SELECT type, COUNT(*) AS n FROM spots GROUP BY type")
    occupied_rows = db.fetch_all(
        "SELECT type, COUNT(*) AS n FROM spots WHERE status = %s GROUP BY type",
        (SPOT_OCCUPIED,))

    occupied_map = {r["type"]: r["n"] for r in occupied_rows}
    by_type = {}
    for r in rows:
        occ = occupied_map.get(r["type"], 0)
        by_type[r["type"]] = {"total": r["n"], "free": r["n"] - occ, "occupied": occ}

    return {"total": total, "free": free, "occupied": total - free, "byType": by_type}


def list_spots(status=None, spot_type=None):
    """车位列表，可按状态与类型筛选。"""
    where, args = [], []
    if status:
        where.append("status = %s")
        args.append(status)
    if spot_type:
        where.append("type = %s")
        args.append(spot_type)
    sql = "SELECT id, code, type, status, plate FROM spots"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY code"
    rows = db.fetch_all(sql, args)
    return {"total": len(rows), "items": rows}


def _find_free_spot(spot_type=None):
    """找一个空闲车位（可指定类型）。找不到返回 None。"""
    sql = "SELECT id, code, type, status FROM spots WHERE status = %s"
    args = [SPOT_FREE]
    if spot_type:
        sql += " AND type = %s"
        args.append(spot_type)
    sql += " ORDER BY code LIMIT 1"
    return db.fetch_one(sql, args)


# ==================================================================
#  停车记录
# ==================================================================
def _open_ticket_of(plate):
    """该车牌当前在场的记录，没有则返回 None。"""
    return db.fetch_one(
        "SELECT id, plate, spot_id, entered_at, status FROM tickets "
        "WHERE plate = %s AND status = %s ORDER BY id DESC LIMIT 1",
        (plate, TICKET_PARKING),
    )


def _validate_plate(plate):
    if not plate or not PLATE_RE.match(plate):
        raise ApiError("INVALID_PLATE", "车牌格式不正确：%s" % plate)


def entry(plate, spot_type=None):
    """车辆入场：校验车牌 -> 找空闲车位 -> 占用 -> 生成停车记录。

    ⚠️ 缺陷 BUG-S3（严重 · 并发）：
      「查空闲车位」和「占用车位」是两次独立的数据库操作，中间没有锁。
      并发请求会在这段窗口里查到**同一个**空闲车位，
      于是同一车位被分配给多辆车 —— 一个车位停进 N 辆车。
      复现方式见 tests/bugs/test_bug_concurrent_entry.py
    """
    _validate_plate(plate)

    if _open_ticket_of(plate):
        raise ApiError("ALREADY_PARKED", "车辆已在场：%s" % plate, 409)

    spot = _find_free_spot(spot_type)
    if spot is None:
        raise ApiError("LOT_FULL", "暂无可用车位", 409)

    # 从「查到车位」到「占用车位」是两步，中间没有加锁保护。
    # 并发请求会在这段窗口里查到同一个空闲车位，于是同一车位被分配给多辆车。
    # 靶场把这段延迟显式化，保证缺陷稳定复现；改成 0 可观察窗口消失后的表现。
    db.simulate_round_trip()

    db.execute(
        "UPDATE spots SET status = %s, plate = %s WHERE id = %s",
        (SPOT_OCCUPIED, plate, spot["id"]),
    )

    entered = _now()
    ticket_id = db.execute(
        "INSERT INTO tickets (plate, spot_id, entered_at, status) "
        "VALUES (%s, %s, %s, %s)",
        (plate, spot["id"], _fmt(entered), TICKET_PARKING),
    )
    db.execute(
        "INSERT INTO spot_logs (spot_id, action, plate, ticket_id, created_at) "
        "VALUES (%s, 'ENTRY', %s, %s, %s)",
        (spot["id"], plate, ticket_id, _fmt(entered)),
    )
    return get_ticket(ticket_id)


def get_ticket(ticket_id):
    ticket = db.fetch_one(
        "SELECT t.id, t.plate, t.spot_id, s.code AS spot_code, s.type AS spot_type, "
        "       t.entered_at, t.exited_at, t.duration_minutes, t.fee, t.status "
        "FROM tickets t JOIN spots s ON s.id = t.spot_id WHERE t.id = %s",
        (ticket_id,),
    )
    if ticket is None:
        raise ApiError("TICKET_NOT_FOUND", "停车记录不存在", 404)
    ticket["fee"] = _money(ticket["fee"])
    ticket["entered_at"] = _fmt(ticket["entered_at"])
    ticket["exited_at"] = _fmt(ticket["exited_at"]) if ticket["exited_at"] else None
    return ticket


def list_tickets(plate=None, status=None):
    """停车记录列表。"""
    where, args = [], []
    if plate:
        where.append("t.plate = %s")
        args.append(plate)
    if status:
        where.append("t.status = %s")
        args.append(status)
    sql = ("SELECT t.id, t.plate, t.spot_id, s.code AS spot_code, "
           "       t.entered_at, t.exited_at, t.duration_minutes, t.fee, t.status "
           "FROM tickets t JOIN spots s ON s.id = t.spot_id")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.id"
    rows = db.fetch_all(sql, args)
    for r in rows:
        r["fee"] = _money(r["fee"])
        r["entered_at"] = _fmt(r["entered_at"])
        r["exited_at"] = _fmt(r["exited_at"]) if r["exited_at"] else None
    return {"total": len(rows), "items": rows}


# ==================================================================
#  计费
# ==================================================================
def calc_fee(seconds):
    """按时长计算停车费。

    规则：15 分钟内免费；超过后首小时 5 元，
    此后每满 1 小时 3 元（不足 1 小时按 1 小时）；单日封顶 40 元。

    ⚠️ 缺陷 BUG-S1（中 · 计费）：
      「不足 1 小时按 1 小时」意味着小时数应当**向上取整**（ceil），
      但这里用的是向下取整（//），导致超出整小时的那部分尾数被抹掉。
      例如停车 61 分钟（3660 秒）：应收 2 小时 = 5 + 3 = 8 元，
      实际只按 1 小时收了 5 元 —— 少收 3 元。
      复现方式见 tests/bugs/test_bug_billing.py
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
    """该车牌是否持有**有效**月卡（可免费出场）。

    ⚠️ 缺陷 BUG-S4（高 · 业务规则）：
      只判断月卡是否存在，**没有比对有效期**。
      于是过期月卡依然免费出场 —— 车场持续漏收。
      复现方式见 tests/bugs/test_bug_card_expiry.py
    """
    card = db.fetch_one(
        "SELECT plate, valid_until FROM month_cards WHERE plate = %s", (plate,))
    if card is None:
        return False
    # 只判断月卡是否存在，没有比对有效期 —— 过期月卡依然免费。
    return True


def exit_vehicle(plate):
    """车辆出场：结算费用 -> 关闭记录 -> 释放车位。

    ⚠️ 缺陷 BUG-S2（高 · 状态机 + 数据一致性）：
      取该车牌最后一条记录时**没有校验它是否已经出场过**，也不做幂等。
      重复调用出场接口会重复执行「释放车位」，
      而且如果此时车位已被**另一辆车**占用，会把别人的车位也一起释放掉。
      复现方式见 tests/bugs/test_bug_exit_state.py
    """
    _validate_plate(plate)

    ticket = db.fetch_one(
        "SELECT id, plate, spot_id, entered_at, status FROM tickets "
        "WHERE plate = %s ORDER BY id DESC LIMIT 1",
        (plate,),
    )
    if ticket is None:
        raise ApiError("TICKET_NOT_FOUND", "未找到该车辆的入场记录", 404)

    # 取该车牌最后一条记录 —— 没有校验它是否已经出场过。
    entered = ticket["entered_at"]
    exited = _now()
    seconds = int((exited - entered).total_seconds())
    if seconds < 0:
        seconds = 0

    fee = 0.0 if _has_free_pass(plate) else calc_fee(seconds)

    db.execute(
        "UPDATE tickets SET exited_at = %s, duration_minutes = %s, fee = %s, "
        "status = %s WHERE id = %s",
        (_fmt(exited), seconds // 60, fee, TICKET_CLOSED, ticket["id"]),
    )

    # 释放车位 —— 重复调用出场接口会重复执行这一步，
    # 即使这个车位此刻已经停着别人的车，也会被一并释放。
    db.execute(
        "UPDATE spots SET status = %s, plate = NULL WHERE id = %s",
        (SPOT_FREE, ticket["spot_id"]),
    )
    db.execute(
        "INSERT INTO spot_logs (spot_id, action, plate, ticket_id, created_at) "
        "VALUES (%s, 'EXIT', %s, %s, %s)",
        (ticket["spot_id"], plate, ticket["id"], _fmt(exited)),
    )

    return get_ticket(ticket["id"])


# ==================================================================
#  月卡
# ==================================================================
def issue_card(plate, valid_until):
    """办理 / 续办月卡。valid_until 形如 2027-12-31。"""
    _validate_plate(plate)
    try:
        datetime.strptime(valid_until, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ApiError("INVALID_DATE", "有效期格式应为 YYYY-MM-DD", 400)

    now = _fmt(_now())
    exists = db.fetch_one("SELECT plate FROM month_cards WHERE plate = %s", (plate,))
    if exists:
        db.execute(
            "UPDATE month_cards SET valid_until = %s, issued_at = %s WHERE plate = %s",
            (valid_until, now, plate),
        )
    else:
        db.execute(
            "INSERT INTO month_cards (plate, valid_until, issued_at) "
            "VALUES (%s, %s, %s)",
            (plate, valid_until, now),
        )
    return get_card(plate)


def get_card(plate):
    card = db.fetch_one(
        "SELECT plate, valid_until, issued_at FROM month_cards WHERE plate = %s",
        (plate,),
    )
    if card is None:
        raise ApiError("CARD_NOT_FOUND", "该车牌未办理月卡", 404)
    card["valid_until"] = card["valid_until"].strftime("%Y-%m-%d")
    card["issued_at"] = _fmt(card["issued_at"])
    # 顺带给出「是否仍在有效期」，方便前端展示。
    # 注意：这个字段只用于展示，不参与 _has_free_pass 的判断。
    card["expired"] = card["valid_until"] < _now().strftime("%Y-%m-%d")
    return card


def list_cards():
    rows = db.fetch_all(
        "SELECT plate, valid_until, issued_at FROM month_cards ORDER BY plate")
    for r in rows:
        r["valid_until"] = r["valid_until"].strftime("%Y-%m-%d")
        r["issued_at"] = _fmt(r["issued_at"])
        r["expired"] = r["valid_until"] < _now().strftime("%Y-%m-%d")
    return {"total": len(rows), "items": rows}


# ==================================================================
#  一致性自检（供测试与排查使用）
# ==================================================================
def consistency_check():
    """检查车场数据是否自洽。

    三条不变量：
      1. 占用车位数  ==  在场记录数
      2. 每个占用车位的 plate 都能对应到一条在场记录
      3. 每个车位「ENTRY 条数 - EXIT 条数」与当前状态一致（占用=1 / 空闲=0）

    任何一条不成立，都说明出现了并发或状态机缺陷。
    """
    problems = []

    occupied = db.fetch_one(
        "SELECT COUNT(*) AS n FROM spots WHERE status = %s", (SPOT_OCCUPIED,))["n"]
    parking = db.fetch_one(
        "SELECT COUNT(*) AS n FROM tickets WHERE status = %s", (TICKET_PARKING,))["n"]
    if occupied != parking:
        problems.append({
            "rule": "occupied_spots_equals_open_tickets",
            "detail": "占用车位 %d 个，但在场记录有 %d 条" % (occupied, parking),
        })

    mismatched = db.fetch_all(
        "SELECT s.code, s.plate FROM spots s "
        "WHERE s.status = %s AND NOT EXISTS ("
        "  SELECT 1 FROM tickets t WHERE t.spot_id = s.id AND t.status = %s"
        ")",
        (SPOT_OCCUPIED, TICKET_PARKING),
    )
    for row in mismatched:
        problems.append({
            "rule": "occupied_spot_has_open_ticket",
            "detail": "车位 %s 显示被 %s 占用，但没有对应的在场记录"
                      % (row["code"], row["plate"]),
        })

    rows = db.fetch_all(
        "SELECT s.id, s.code, s.status, "
        "  (SELECT COUNT(*) FROM spot_logs l "
        "   WHERE l.spot_id = s.id AND l.action = 'ENTRY') AS en, "
        "  (SELECT COUNT(*) FROM spot_logs l "
        "   WHERE l.spot_id = s.id AND l.action = 'EXIT') AS ex "
        "FROM spots s"
    )
    for row in rows:
        net = row["en"] - row["ex"]
        expect = 1 if row["status"] == SPOT_OCCUPIED else 0
        if net != expect:
            problems.append({
                "rule": "spot_logs_balance",
                "detail": "车位 %s 当前 %s，流水净占用 %d（应为 %d）"
                          % (row["code"], row["status"], net, expect),
            })

    return {"ok": len(problems) == 0, "problems": problems}

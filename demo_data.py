# -*- coding: utf-8 -*-
"""智能停车管理系统 · 演示数据生成

给项目灌一批「像真在运营」的数据：

    车位     7  →  80 个（A / B / C 三个区，含无障碍位与充电位）
    月卡     2  →  24 张（其中 5 张已过期）
    停车记录 0  → 320 条（270 条已出场 + 50 条正在场内）
    车位流水 0  → 590 条

用法：
    python demo_data.py          # 灌演示数据（会先重置为初始状态）
    python demo_data.py clear    # 清掉演示数据，回到 sql/seed.sql 的干净基线

设计要点（也是可以直接拿来验证的不变量）：
    1. 每个车位的 (ENTRY 条数 - EXIT 条数) 只能是 0 或 1；
    2. 它必须与车位当前状态吻合：OCCUPIED → 1，FREE → 0；
    3. spots.plate 必须等于占用它的那张 PARKING 票的车牌；
    4. 同一车牌不能同时有两张 PARKING 票；
    5. 停车费按 service.calc_fee 的规则算，duration_minutes 与 fee 自洽。
"""
import datetime
import random
import sys

import config
import db
import init_db

random.seed(20261009)

# ----------------------------------------------------------------------
# 车位：A 区 30 个普通、B 区 25 个（含 5 个无障碍）、C 区 25 个（含 8 个充电）
# ----------------------------------------------------------------------
AREAS = [
    ("A", 1, 30, "NORMAL"),
    ("B", 1, 5, "ACCESSIBLE"),
    ("B", 6, 25, "NORMAL"),
    ("C", 1, 8, "CHARGING"),
    ("C", 9, 25, "NORMAL"),
]

PROVINCES = "京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川贵云陕甘青宁新"
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"

CLOSED_COUNT = 270
PARKING_COUNT = 50
CARD_VALID = 17
CARD_EXPIRED = 5


def _plate(used=None):
    """随机生成一个合规车牌：省份简称 + 字母 + 5 位数字。"""
    while True:
        p = random.choice(PROVINCES) + random.choice(LETTERS) + \
            "%05d" % random.randint(0, 99999)
        if used is None or p not in used:
            return p


def _now():
    return datetime.datetime.now()


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _calc_fee(seconds):
    """与 service.calc_fee 同一套规则（15 分钟免费 / 首小时 5 元 / 每小时 3 元 / 封顶 40）。"""
    if seconds <= config.FREE_SECONDS:
        return 0.0
    hours = int(seconds // 3600)
    if hours < 1:
        hours = 1
    return min(config.FIRST_HOUR_FEE + (hours - 1) * config.PER_HOUR_FEE,
               config.DAILY_CAP)


def _count(table):
    return db.fetch_one("SELECT COUNT(*) AS n FROM " + table)["n"]


# ======================================================================
#  生成
# ======================================================================
def build():
    init_db.reset_data()
    print("  [1/6] 已重置为初始数据（sql/seed.sql）")

    # ---- 车位 ----
    # 用 INSERT IGNORE：seed.sql 里已有的 7 个车位保持原样，只补新增的编号
    for area, start, end, stype in AREAS:
        for i in range(start, end + 1):
            db.execute(
                "INSERT IGNORE INTO spots (code, type, status, plate) "
                "VALUES (%s, %s, 'FREE', NULL)",
                ("%s-%03d" % (area, i), stype),
            )
    spots = db.fetch_all("SELECT id, code, type FROM spots ORDER BY id")
    print("  [2/6] 车位：%d 个" % len(spots))

    # ---- 历史停车记录（已出场）----
    now = _now()
    for _ in range(CLOSED_COUNT):
        spot = random.choice(spots)
        plate = _plate()

        dur = random.choice([
            random.randint(60, config.FREE_SECONDS),          # 15 分钟内免费
            random.randint(config.FREE_SECONDS + 1, 5400),    # 15 分 ~ 1.5 小时
            random.randint(5400, 3600 * 12),                  # 1.5 ~ 12 小时
            random.randint(3600 * 12, 3600 * 30),             # 半天以上
        ])
        entered = now - datetime.timedelta(seconds=dur) - \
            datetime.timedelta(days=random.randint(0, 60),
                               minutes=random.randint(0, 720))
        exited = entered + datetime.timedelta(seconds=dur)
        minutes = int(dur // 60)
        fee = _calc_fee(dur)

        tid = db.execute(
            "INSERT INTO tickets (plate, spot_id, entered_at, exited_at, "
            "                     duration_minutes, fee, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'CLOSED')",
            (plate, spot["id"], _fmt(entered), _fmt(exited), minutes, fee),
        )
        db.execute(
            "INSERT INTO spot_logs (spot_id, action, plate, ticket_id, created_at) "
            "VALUES (%s, 'ENTRY', %s, %s, %s)",
            (spot["id"], plate, tid, _fmt(entered)),
        )
        db.execute(
            "INSERT INTO spot_logs (spot_id, action, plate, ticket_id, created_at) "
            "VALUES (%s, 'EXIT', %s, %s, %s)",
            (spot["id"], plate, tid, _fmt(exited)),
        )
    print("  [3/6] 历史停车记录：%d 条（全部已出场）" % CLOSED_COUNT)

    # ---- 正在场内的车（占用车位）----
    used_plates = set()
    occupied = random.sample(spots, PARKING_COUNT)
    for spot in occupied:
        plate = _plate(used_plates)
        used_plates.add(plate)

        entered = now - datetime.timedelta(
            seconds=random.randint(config.FREE_SECONDS + 1, 3600 * 72),
            minutes=random.randint(0, 59),
        )

        tid = db.execute(
            "INSERT INTO tickets (plate, spot_id, entered_at, exited_at, "
            "                     duration_minutes, fee, status) "
            "VALUES (%s, %s, %s, NULL, NULL, NULL, 'PARKING')",
            (plate, spot["id"], _fmt(entered)),
        )
        db.execute(
            "UPDATE spots SET status = 'OCCUPIED', plate = %s WHERE id = %s",
            (plate, spot["id"]),
        )
        db.execute(
            "INSERT INTO spot_logs (spot_id, action, plate, ticket_id, created_at) "
            "VALUES (%s, 'ENTRY', %s, %s, %s)",
            (spot["id"], plate, tid, _fmt(entered)),
        )
    print("  [4/6] 在场记录：%d 条（对应 %d 个已占用车位）" % (PARKING_COUNT, PARKING_COUNT))

    # ---- 月卡 ----
    #   一半的月卡给「正在场内」的车牌，另一半给随机车牌
    holders = random.sample(sorted(used_plates), min(10, len(used_plates)))
    taken = set(used_plates) | set(holders)
    others = []
    while len(others) < CARD_VALID + CARD_EXPIRED - len(holders):
        p = _plate(taken)
        taken.add(p)
        others.append(p)
    all_plates = holders + others

    for i, plate in enumerate(all_plates):
        if i < CARD_EXPIRED:
            # 前 5 张做成已过期，用来复现 BUG-S4
            valid = (now - datetime.timedelta(days=random.randint(20, 300))).date()
        else:
            valid = (now + datetime.timedelta(days=random.randint(15, 330))).date()
        db.execute(
            "INSERT IGNORE INTO month_cards (plate, valid_until, issued_at) "
            "VALUES (%s, %s, %s)",
            (plate, valid.isoformat(),
             _fmt(now - datetime.timedelta(days=random.randint(30, 400)))),
        )
    print("  [5/6] 月卡：%d 张（含 %d 张已过期）" % (_count("month_cards"), CARD_EXPIRED))

    print("  [6/6] 车位流水：%d 条" % _count("spot_logs"))
    print("")
    print("  完成。当前数据量：")
    for t in ("spots", "tickets", "spot_logs", "month_cards"):
        print("    %-14s %s" % (t, _count(t)))


def clear():
    init_db.reset_data()
    print("  已清掉演示数据，恢复到 sql/seed.sql 的干净基线。")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        clear()
    else:
        build()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print("")
        print("  [错误] 生成演示数据失败：%s" % exc)
        sys.exit(1)

# -*- coding: utf-8 -*-
"""智能停车管理系统 · 内存数据层

用 Python 字典模拟关系库的表，进程内共享。不依赖任何数据库服务，
克隆下来直接就能跑；进程退出后数据重置。

"表"结构：
    spots       车位（编号 / 类型 / 状态）
    tickets     停车记录（车牌 / 车位 / 入场出场时间 / 费用 / 状态）
    cards       月卡（车牌 / 有效期）
"""
import itertools


# 车位类型
SPOT_NORMAL = "NORMAL"          # 普通车位
SPOT_ACCESSIBLE = "ACCESSIBLE"  # 无障碍车位
SPOT_CHARGING = "CHARGING"      # 充电车位

# 车位状态
SPOT_FREE = "FREE"
SPOT_OCCUPIED = "OCCUPIED"

# 停车记录状态
TICKET_PARKING = "PARKING"      # 在场
TICKET_CLOSED = "CLOSED"        # 已出场


class Store(object):
    def __init__(self):
        self.reset()

    def reset(self):
        """清空并重新装载基础数据。测试中每个用例前会调用。"""
        self.spots = {}       # spot_id -> dict
        self.tickets = {}     # ticket_id -> dict
        self.cards = {}       # plate -> dict
        self._seq = itertools.count(1)
        self._seed_spots()

    def next_id(self, prefix):
        """业务主键生成器，形如 SP00001 / TK00007。"""
        return "%s%05d" % (prefix, next(self._seq))

    def _seed_spots(self):
        """预置车位。

        刻意把车位总量压得很小，且只有 1 个充电车位 ——
        方便观察「车位耗尽」与「并发争抢」这类边界行为。
        """
        layout = [
            ("A", SPOT_NORMAL, 4),
            ("B", SPOT_ACCESSIBLE, 2),
            ("C", SPOT_CHARGING, 1),
        ]
        for zone, spot_type, count in layout:
            for i in range(1, count + 1):
                sid = self.next_id("SP")
                self.spots[sid] = {
                    "id": sid,
                    "code": "%s-%03d" % (zone, i),
                    "type": spot_type,
                    "status": SPOT_FREE,
                    "plate": None,
                }


# 全局单例：整个服务共用一个 Store
store = Store()

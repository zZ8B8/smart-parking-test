# -*- coding: utf-8 -*-
"""智能停车管理系统 · 数据访问层

职责：把「连数据库、执行 SQL、拿结果」这些事封装起来，
业务层（service.py）只写 SQL 语句，不关心连接从哪来。

为什么不每个请求新建连接：
    本机 MariaDB 在 skip_name_resolve=OFF 时，每建一次连接都要做反向 DNS 解析
    （约 0.27 秒）。20 个并发请求各建一次连接，请求就会被串行化到 5 秒以上，
    并发测试的竞态窗口被彻底冲散，缺陷反而复现不出来。
    所以这里用连接池：进程启动时预建一批连接，请求来了直接借、用完还。
"""
import pymysql
from pymysql.cursors import DictCursor

import config

# ==================================================================
#  单连接
# ==================================================================
def connect(with_db=True):
    """新建一个数据库连接（autocommit=True，查询立刻可见）。"""
    cfg = config.DB_CONFIG if with_db else config.DB_CONFIG_NO_DB
    return pymysql.connect(cursorclass=DictCursor, autocommit=True, **cfg)


# ==================================================================
#  连接池
# ==================================================================
class ConnectionPool(object):
    """极简连接池：queue 存放空闲连接，借出 / 归还。

    没有做复杂的健康检查与扩容，够用即可 ——
    目标是「让并发请求不必各自等待 0.27 秒的连接建立时间」。
    """

    def __init__(self, size, with_db=True):
        import queue
        self._queue = queue.Queue(maxsize=size)
        self._size = size
        self._with_db = with_db
        self._created = 0

    def warm_up(self):
        """启动预热：一次性建满 size 个连接放进池子。"""
        while self._created < self._size:
            self._queue.put(connect(self._with_db))
            self._created += 1

    def acquire(self, timeout=30):
        import queue
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            # 池子被占满且超时：兜底新建一个，避免请求直接失败
            return connect(self._with_db)

    def release(self, conn):
        """归还连接。归还前 ping 一下，坏连接直接丢弃重建。"""
        import queue
        try:
            conn.ping()
        except Exception:  # noqa: BLE001
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                conn = connect(self._with_db)
            except Exception:  # noqa: BLE001
                return
        try:
            self._queue.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


_pools = {}


def get_pool(with_db=True):
    """按「是否带库名」取连接池（单例），首次调用时自动预热。"""
    key = bool(with_db)
    pool = _pools.get(key)
    if pool is None:
        pool = ConnectionPool(config.DB_POOL_SIZE, with_db)
        pool.warm_up()
        _pools[key] = pool
    return pool


# ==================================================================
#  查询封装
# ==================================================================
class _Cursor(object):
    """上下文管理器：从池子里借连接 -> 借出游标 -> 用完归还。"""

    def __init__(self, with_db=True):
        self.with_db = with_db

    def __enter__(self):
        self.conn = get_pool(self.with_db).acquire()
        self.cur = self.conn.cursor()
        return self.cur

    def __exit__(self, exc_type, exc, tb):
        try:
            self.cur.close()
        except Exception:  # noqa: BLE001
            pass
        get_pool(self.with_db).release(self.conn)
        return False


def cursor(with_db=True):
    return _Cursor(with_db)


def fetch_all(sql, args=None, with_db=True):
    with cursor(with_db) as cur:
        cur.execute(sql, args or ())
        return list(cur.fetchall())


def fetch_one(sql, args=None, with_db=True):
    with cursor(with_db) as cur:
        cur.execute(sql, args or ())
        return cur.fetchone()


def execute(sql, args=None, with_db=True):
    """执行写入语句，返回自增主键（INSERT）或影响行数（UPDATE/DELETE）。"""
    with cursor(with_db) as cur:
        cur.execute(sql, args or ())
        if cur.lastrowid:
            return cur.lastrowid
        return cur.rowcount


def ping():
    """返回数据库版本号，用于健康检查。"""
    row = fetch_one("SELECT VERSION() AS v", with_db=False)
    return row["v"]


# ==================================================================
#  并发缺陷用的「人为延迟」
# ==================================================================
def simulate_round_trip():
    """模拟一次持久层往返的时间消耗。

    真实系统里两次 SQL 之间必然有网络 + 磁盘时间，那就是竞态窗口。
    本机数据库太快导致窗口趋近于 0，缺陷变成偶现；这里把它显式化，
    保证并发缺陷能稳定复现。设 config.SIMULATE_DB_LATENCY = 0 即可关闭。
    """
    import time
    delay = config.SIMULATE_DB_LATENCY
    if delay > 0:
        time.sleep(delay)

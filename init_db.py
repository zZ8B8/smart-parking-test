# -*- coding: utf-8 -*-
"""智能停车管理系统 · 数据库初始化

用法：
    python init_db.py          # 建库 + 建表 + 灌初始数据
    python init_db.py reset    # 只重置数据（表已存在时快得多）

做两件事：
    1. 执行 sql/schema.sql —— 建库、建表（不连库，因为库还不存在）
    2. 执行 sql/seed.sql   —— 清空并写入初始数据（连到库上执行）
"""
import os
import sys

import pymysql
from pymysql.cursors import DictCursor

import config
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_FILE = os.path.join(BASE_DIR, "sql", "schema.sql")
SEED_FILE = os.path.join(BASE_DIR, "sql", "seed.sql")


def _run(sql_file, with_db):
    """按分号切分 SQL 文件并逐条执行。

    用独立的连接（不走连接池）：建库、DROP TABLE 这类 DDL
    不应该占用请求池里的连接。
    """
    with open(sql_file, "r", encoding="utf-8") as fh:
        content = fh.read()

    # 去掉注释行，避免把注释里的分号也当成语句分隔
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        lines.append(line)
    content = "\n".join(lines)

    statements = [s.strip() for s in content.split(";") if s.strip()]

    conn = db.connect(with_db)
    try:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
    finally:
        conn.close()
    return len(statements)


def init_database():
    """建库 + 建表 + 灌数据。"""
    n1 = _run(SCHEMA_FILE, with_db=False)
    n2 = _run(SEED_FILE, with_db=True)
    print("  schema.sql ：执行 %d 条语句（建库 + 建表）" % n1)
    print("  seed.sql   ：执行 %d 条语句（初始数据）" % n2)


def reset_data():
    """只重置数据，不重建表。测试中每条用例前调用。"""
    _run(SEED_FILE, with_db=True)
    import service
    service.reset_clock()


def main():
    print("=" * 62)
    print("  智能停车管理系统 · 数据库初始化")
    print("=" * 62)
    print("  目标：%s:%s / %s" % (
        config.DB_CONFIG["host"], config.DB_CONFIG["port"], config.DB_CONFIG["database"]))
    print("-" * 62)

    mode = sys.argv[1] if len(sys.argv) > 1 else "init"
    try:
        if mode == "reset":
            reset_data()
            print("  数据已重置为初始状态")
        else:
            init_database()
            print("  初始化完成")
    except pymysql.err.OperationalError as exc:
        print("")
        print("  [错误] 连不上数据库：%s" % exc)
        print("  请检查：")
        print("    1. MySQL / MariaDB 是否已启动")
        print("    2. config.py 里的账号密码是否正确")
        print("       （当前：%s / %s）" % (
            config.DB_CONFIG["user"], config.DB_CONFIG["password"]))
        print("")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print("")
        print("  [错误] 初始化失败：%s" % exc)
        print("")
        sys.exit(1)

    print("-" * 62)
    print("  下一步：python app.py")
    print("  然后打开 http://127.0.0.1:%d/" % config.SERVER_PORT)
    print("=" * 62)


if __name__ == "__main__":
    main()

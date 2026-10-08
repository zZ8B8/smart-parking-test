# -*- coding: utf-8 -*-
"""一键跑测试（由同目录的「一键运行测试.bat」调用）。

流程：
  1. 检查 pytest 是否可用，缺了就自动装
  2. 检查数据库是否建好，没建好先跑 init_db.py
  3. 执行 python -m pytest

所有中文提示都由本脚本打印 —— .bat 里只放 ASCII。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

PROJECT_NAME = "智能停车 smart-parking-test"
PROBE_TABLE = "spots"             # 用这张表判断数据库建好没有
PIP_PACKAGE = "pytest"
EXTRA_REQUIREMENTS = ["Flask", "PyMySQL"]


def _out():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run(args, timeout=None):
    return subprocess.run(args, cwd=HERE, timeout=timeout)


def run_capture(args, timeout=None):
    return subprocess.run(args, cwd=HERE, capture_output=True, timeout=timeout)


def main():
    _out()
    py = sys.argv[1] if len(sys.argv) > 1 else sys.executable

    print("=" * 66)
    print("  %s · 一键运行测试" % PROJECT_NAME)
    print("=" * 66)
    print("  Python：%s" % py)
    print("-" * 66)

    # ---- 1. 依赖 ----
    r = run_capture([py, "-c", "import pytest, flask, pymysql"])
    if r.returncode != 0:
        print("发现依赖缺失，正在安装：%s ..." % ", ".join([PIP_PACKAGE] + EXTRA_REQUIREMENTS))
        run([py, "-m", "pip", "install", "--quiet",
             PIP_PACKAGE] + EXTRA_REQUIREMENTS)
        r = run_capture([py, "-c", "import pytest, flask, pymysql"])
        if r.returncode != 0:
            print("")
            print("  [错误] 依赖安装失败。请手动执行：")
            print("     %s -m pip install -r requirements.txt" % py)
            print("")
            return 1
        print("  依赖已装好。")
    else:
        print("  依赖检查：pytest / Flask / PyMySQL 都已就绪。")

    # ---- 2. 数据库 ----
    probe = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import db\n"
        "db.fetch_one('SELECT COUNT(*) AS n FROM `%s`' % sys.argv[2])\n"
        "print('DB_OK')\n"
    )
    r = run_capture([py, "-c", probe, HERE, PROBE_TABLE], timeout=60)
    if r.returncode != 0 or b"DB_OK" not in (r.stdout or b""):
        print("  数据库还没建好，正在初始化（建库 + 建表 + 灌初始数据）...")
        r2 = run([py, "init_db.py"], timeout=180)
        if r2.returncode != 0:
            print("")
            print("  [错误] 数据库初始化失败，通常是 MySQL 没启动或密码不对。")
            print("     数据库配置在 config.py，默认 root / 123456")
            print("")
            return 1
        print("  数据库已就绪。")
    else:
        print("  数据库检查：已就绪（数据会在测试中自动重置）。")

    print("-" * 66)
    print("  开始执行 pytest ...")
    print("-" * 66)

    # ---- 3. 跑测试 ----
    rc = run([py, "-m", "pytest", "-q"]).returncode

    print("")
    print("=" * 66)
    if rc == 0:
        print("  全部通过（黄色 XFAIL 是刻意留的缺陷回归守护，属正常）。")
    elif rc == 5:
        print("  没有收集到任何用例，检查 tests/ 目录是否完整。")
    else:
        print("  有测试未通过（返回码 %s）。" % rc)
        print("  想看详细失败原因，在仓库目录执行：")
        print("     %s -m pytest -v --tb=long" % py)
    print("=" * 66)
    return rc


if __name__ == "__main__":
    sys.exit(main())

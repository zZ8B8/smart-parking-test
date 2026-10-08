# -*- coding: utf-8 -*-
"""智能停车管理系统 · Web 服务入口

一个停车场管理系统：前端页面 + JSON 接口，数据存在 MySQL。

启动：
    python app.py                  # 监听 127.0.0.1:5002
    python app.py 8080             # 指定端口

统一响应格式：
    成功  {"code": "OK", "data": ...}
    失败  {"code": "错误码", "message": "错误描述"}      HTTP 状态码 4xx
"""
import sys

from flask import Flask, jsonify, render_template, request

import config
import db
import service
from service import ApiError

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


def ok(data=None):
    return jsonify({"code": "OK", "data": data})


@app.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify({"code": err.code, "message": err.message}), err.http_status


@app.errorhandler(404)
def handle_404(_err):
    if request.path.startswith("/api/"):
        return jsonify({"code": "NOT_FOUND", "message": "接口不存在"}), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
def handle_500(err):
    return jsonify({"code": "INTERNAL_ERROR", "message": str(err)}), 500


def body():
    return request.get_json(silent=True) or {}


# ==================================================================
#  页面路由
# ==================================================================
@app.route("/")
def page_index():
    return render_template("index.html")


@app.route("/entry")
def page_entry():
    return render_template("entry.html")


@app.route("/exit")
def page_exit():
    return render_template("exit.html")


@app.route("/tickets")
def page_tickets():
    return render_template("tickets.html")


@app.route("/card")
def page_card():
    return render_template("card.html")


# ==================================================================
#  接口 · 系统
# ==================================================================
@app.route("/health")
def health():
    return ok({"status": "UP", "db": db.ping()})


@app.route("/api/dev/reset", methods=["POST"])
def dev_reset():
    """把数据恢复到初始状态（含重置时钟偏移）。仅用于测试。"""
    import init_db

    init_db.reset_data()
    service.reset_clock()
    return ok({"reset": True})


@app.route("/api/dev/clock", methods=["GET", "POST"])
def dev_clock():
    """测试用时钟控制。

    POST {"advance": 3600}  把时钟前移 3600 秒（累加）
    POST {"reset": true}    归零
    GET                     查看当前偏移与虚拟时间
    """
    if request.method == "POST":
        b = body()
        if b.get("reset"):
            service.reset_clock()
        elif b.get("advance") is not None:
            service.advance_clock(b.get("advance"))
        else:
            raise ApiError("INVALID_PARAM", "请提供 advance 或 reset", 400)
    return ok(service.clock_state())


@app.route("/api/consistency")
def api_consistency():
    """车场数据一致性自检。ok=false 说明出现了并发/状态机缺陷。"""
    return ok(service.consistency_check())


# ==================================================================
#  接口 · 车位
# ==================================================================
@app.route("/api/lot/summary")
def api_lot_summary():
    return ok(service.lot_summary())


@app.route("/api/spots")
def api_spots():
    q = request.args
    return ok(service.list_spots(status=q.get("status"), spot_type=q.get("type")))


# ==================================================================
#  接口 · 车辆进出
# ==================================================================
@app.route("/api/vehicles/entry", methods=["POST"])
def api_entry():
    b = body()
    return ok(service.entry(b.get("plate"), b.get("spotType")))


@app.route("/api/vehicles/exit", methods=["POST"])
def api_exit():
    return ok(service.exit_vehicle(body().get("plate")))


# ==================================================================
#  接口 · 停车记录
# ==================================================================
@app.route("/api/tickets")
def api_tickets():
    q = request.args
    return ok(service.list_tickets(plate=q.get("plate"), status=q.get("status")))


@app.route("/api/tickets/<int:ticket_id>")
def api_ticket_detail(ticket_id):
    return ok(service.get_ticket(ticket_id))


# ==================================================================
#  接口 · 月卡
# ==================================================================
@app.route("/api/cards", methods=["GET"])
def api_cards():
    return ok(service.list_cards())


@app.route("/api/cards", methods=["POST"])
def api_issue_card():
    b = body()
    return ok(service.issue_card(b.get("plate"), b.get("validUntil")))


@app.route("/api/cards/<plate>")
def api_get_card(plate):
    return ok(service.get_card(plate))


# ==================================================================
#  启动
# ==================================================================
def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else config.SERVER_PORT

    try:
        ver = db.ping()
    except Exception as exc:  # noqa: BLE001
        print("")
        print("  [错误] 连不上数据库：%s" % exc)
        print("  请先确认 MySQL 已启动，然后运行：python init_db.py")
        print("")
        sys.exit(1)

    print("=" * 62)
    print("  智能停车管理系统 · 服务已启动")
    print("=" * 62)
    print("  数据库   ：MySQL %s @ %s:%s/%s" % (
        ver, config.DB_CONFIG["host"], config.DB_CONFIG["port"],
        config.DB_CONFIG["database"]))
    print("  车场总览 ：http://127.0.0.1:%d/" % port)
    print("  健康检查 ：http://127.0.0.1:%d/health" % port)
    print("  接口文档 ：docs/02-接口文档.md")
    print("-" * 62)
    print("  按 Ctrl+C 停止服务")
    print("=" * 62)
    app.run(host=config.SERVER_HOST, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()

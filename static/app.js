/* 智能停车管理系统 · 前端公共库
 *
 * 零依赖：不引 jQuery / Vue，纯原生 fetch。
 * 暴露一个全局对象 PK，页面脚本用它调接口、渲染提示。
 */
(function (global) {
  "use strict";

  var PK = {};

  /* ------------------------------------------------------------
   *  接口调用
   * ---------------------------------------------------------- */
  function request(method, path, body) {
    var opts = {
      method: method,
      headers: { "Content-Type": "application/json" }
    };
    if (body !== undefined && body !== null) {
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (resp) {
      return resp.json().catch(function () {
        throw new Error("服务返回了非 JSON 内容（HTTP " + resp.status + "）");
      }).then(function (json) {
        if (!resp.ok || json.code !== "OK") {
          var err = new Error(json.message || ("请求失败 HTTP " + resp.status));
          err.code = json.code;
          err.status = resp.status;
          throw err;
        }
        return json.data;
      });
    });
  }

  PK.request = request;
  PK.get = function (p) { return request("GET", p); };
  PK.post = function (p, b) { return request("POST", p, b || {}); };
  PK.put = function (p, b) { return request("PUT", p, b || {}); };
  PK.del = function (p) { return request("DELETE", p); };

  /* ------------------------------------------------------------
   *  工具函数
   * ---------------------------------------------------------- */
  PK.esc = function (s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  PK.money = function (n) {
    if (n === null || n === undefined) return "—";
    return "¥" + Number(n).toFixed(2);
  };

  PK.spotTypeText = function (t) {
    return { NORMAL: "普通", ACCESSIBLE: "无障碍", CHARGING: "充电" }[t] || t;
  };

  PK.ticketStatusText = function (s) {
    return { PARKING: "在场", CLOSED: "已出场" }[s] || s;
  };

  PK.ticketBadge = function (s) {
    var cls = s === "PARKING" ? "badge badge-blue" : "badge badge-gray";
    return '<span class="' + cls + '">' + PK.esc(PK.ticketStatusText(s)) + "</span>";
  };

  PK.plateChip = function (p) {
    return '<span class="plate">' + PK.esc(p) + "</span>";
  };

  /* 秒 -> 「X 小时 Y 分钟」 */
  PK.duration = function (seconds) {
    if (seconds === null || seconds === undefined) return "—";
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return h + " 小时 " + m + " 分钟";
    return m + " 分钟";
  };

  /* ------------------------------------------------------------
   *  消息提示
   * ---------------------------------------------------------- */
  PK.alert = function (message, type) {
    var box = document.getElementById("alert-box");
    if (!box) return;
    var cls = type === "error" ? "alert alert-error"
            : type === "ok" ? "alert alert-ok" : "alert alert-info";
    box.innerHTML = '<div class="' + cls + '">' + PK.esc(message) + "</div>";
    window.clearTimeout(PK._alertTimer);
    PK._alertTimer = window.setTimeout(function () { box.innerHTML = ""; }, 6000);
  };

  /* ------------------------------------------------------------
   *  导航高亮
   * ---------------------------------------------------------- */
  PK.markNav = function (page) {
    var links = document.querySelectorAll(".nav-links a");
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute("data-page") === page) {
        links[i].className = "active";
      }
    }
  };

  /* ------------------------------------------------------------
   *  测试时钟：显示 / 前移
   * ---------------------------------------------------------- */
  PK.refreshClock = function () {
    return PK.get("/api/dev/clock").then(function (d) {
      var chip = document.getElementById("clock-chip");
      if (!chip) return d;
      if (d.offsetSeconds > 0) {
        chip.innerHTML = '<span class="clock-warn">时钟已前移 ' +
          PK.duration(d.offsetSeconds) + "</span>";
      } else {
        chip.textContent = d.virtualNow;
      }
      return d;
    });
  };

  PK.advanceClock = function (seconds) {
    return PK.post("/api/dev/clock", { advance: seconds }).then(function (d) {
      PK.refreshClock();
      return d;
    });
  };

  /* 生成「拨快时间」按钮组，供页面复用 */
  PK.clockControls = function () {
    var presets = [
      { label: "+10 分钟", s: 600 },
      { label: "+1 小时", s: 3600 },
      { label: "+3 小时", s: 10800 },
      { label: "+25 小时", s: 90000 }
    ];
    var html = '<div class="clock-bar"><span class="clock-bar-label">测试时钟：</span>';
    presets.forEach(function (p) {
      html += '<button class="btn btn-ghost btn-sm" data-adv="' + p.s + '">' +
        p.label + "</button>";
    });
    html += '<button class="btn btn-ghost btn-sm" data-adv="0" data-reset="1">归零</button>';
    html += '<span class="hint">先在「入场登记」停车，再拨快时间，最后「出场结算」看费用</span></div>';
    return html;
  };

  PK.bindClockControls = function (root) {
    var scope = root || document;
    var btns = scope.querySelectorAll("[data-adv]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].onclick = function () {
        var self = this;
        var reset = self.getAttribute("data-reset") === "1";
        var p = reset
          ? PK.post("/api/dev/clock", { reset: true })
          : PK.advanceClock(parseInt(self.getAttribute("data-adv"), 10));
        p.then(function () {
          PK.alert(reset ? "测试时钟已归零" : "测试时钟已前移", "ok");
          if (typeof PK.onClockChanged === "function") PK.onClockChanged();
        }).catch(function (e) { PK.alert(e.message, "error"); });
      };
    }
  };

  /* ------------------------------------------------------------
   *  通用初始化
   * ---------------------------------------------------------- */
  PK.init = function (page) {
    PK.markNav(page);
    PK.refreshClock().catch(function () {
      var chip = document.getElementById("clock-chip");
      if (chip) chip.textContent = "服务未连接";
    });

    var btn = document.getElementById("btn-reset");
    if (btn) {
      btn.onclick = function () {
        if (!window.confirm("确定把数据恢复到初始状态吗？\n（所有车位、停车记录、月卡都会重置，测试时钟归零）")) return;
        PK.post("/api/dev/reset", {}).then(function () {
          PK.alert("数据已重置", "ok");
          PK.refreshClock();
          if (typeof PK.onClockChanged === "function") PK.onClockChanged();
          window.setTimeout(function () { window.location.reload(); }, 600);
        }).catch(function (e) { PK.alert(e.message, "error"); });
      };
    }
  };

  global.PK = PK;
})(window);

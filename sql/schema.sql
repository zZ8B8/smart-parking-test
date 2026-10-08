-- ============================================================
--  智能停车管理系统 · 建库建表脚本
--  数据库：smart_parking      字符集：utf8mb4      引擎：InnoDB
-- ============================================================

CREATE DATABASE IF NOT EXISTS smart_parking
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_general_ci;

USE smart_parking;

-- 先删后建，保证可重复执行
DROP TABLE IF EXISTS spot_logs;
DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS month_cards;
DROP TABLE IF EXISTS spots;

-- ------------------------------------------------------------
-- 车位表
-- ------------------------------------------------------------
CREATE TABLE spots (
    id          INT AUTO_INCREMENT PRIMARY KEY COMMENT '车位ID',
    code        VARCHAR(16)  NOT NULL COMMENT '车位编号，如 A-001',
    type        VARCHAR(20)  NOT NULL COMMENT '类型：NORMAL/ACCESSIBLE/CHARGING',
    status      VARCHAR(20)  NOT NULL DEFAULT 'FREE' COMMENT '状态：FREE/OCCUPIED',
    plate       VARCHAR(20)  NULL COMMENT '当前占用车牌，空闲为 NULL',
    UNIQUE KEY uk_spots_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='车位';

-- ------------------------------------------------------------
-- 停车记录表
-- ------------------------------------------------------------
CREATE TABLE tickets (
    id               INT AUTO_INCREMENT PRIMARY KEY COMMENT '记录ID',
    plate            VARCHAR(20)  NOT NULL COMMENT '车牌',
    spot_id          INT          NOT NULL COMMENT '分配的车位ID',
    entered_at       DATETIME     NOT NULL COMMENT '入场时间',
    exited_at        DATETIME     NULL COMMENT '出场时间',
    duration_minutes INT          NULL COMMENT '停车时长（分钟）',
    fee              DECIMAL(10,2) NULL COMMENT '停车费',
    status           VARCHAR(20)  NOT NULL DEFAULT 'PARKING' COMMENT '状态：PARKING/CLOSED',
    KEY idx_tickets_plate (plate),
    KEY idx_tickets_status (status),
    CONSTRAINT fk_tickets_spot FOREIGN KEY (spot_id) REFERENCES spots (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='停车记录';

-- ------------------------------------------------------------
-- 月卡表
-- ------------------------------------------------------------
CREATE TABLE month_cards (
    plate       VARCHAR(20) NOT NULL PRIMARY KEY COMMENT '车牌',
    valid_until DATE        NOT NULL COMMENT '有效期至',
    issued_at   DATETIME    NOT NULL COMMENT '办理时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='月卡';

-- ------------------------------------------------------------
-- 车位流水表（审计用）
-- ------------------------------------------------------------
-- 每一次「占用」和「释放」都记一条。
-- 反向校验公式：对任一车位，
--   (ENTRY 条数 - EXIT 条数) 应等于 1（当前占用）/ 0（当前空闲）
-- 若不等，说明出现了「重复释放」「一车位发多车」这类不一致。
CREATE TABLE spot_logs (
    id         INT AUTO_INCREMENT PRIMARY KEY COMMENT '流水ID',
    spot_id    INT         NOT NULL COMMENT '车位ID',
    action     VARCHAR(20) NOT NULL COMMENT '动作：ENTRY/EXIT',
    plate      VARCHAR(20) NOT NULL COMMENT '车牌',
    ticket_id  INT         NULL COMMENT '关联停车记录',
    created_at DATETIME    NOT NULL COMMENT '发生时间',
    KEY idx_logs_spot (spot_id),
    CONSTRAINT fk_logs_spot FOREIGN KEY (spot_id) REFERENCES spots (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='车位流水';

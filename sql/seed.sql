-- ============================================================
--  智能停车管理系统 · 初始数据
--  用 DELETE 而不是 TRUNCATE：TRUNCATE 受外键约束限制，
--  且 DDL 开销大；测试中每条用例前都要重置一次，DELETE 更快。
-- ============================================================

USE smart_parking;

SET FOREIGN_KEY_CHECKS = 0;
DELETE FROM spot_logs;
DELETE FROM tickets;
DELETE FROM month_cards;
DELETE FROM spots;
ALTER TABLE spots AUTO_INCREMENT = 1;
ALTER TABLE tickets AUTO_INCREMENT = 1;
ALTER TABLE spot_logs AUTO_INCREMENT = 1;
SET FOREIGN_KEY_CHECKS = 1;

-- ------------------------------------------------------------
-- 车位：刻意压得很小 —— 共 7 个，且只有 1 个充电车位
-- 方便观察「车位耗尽」与「并发争抢」这类边界行为
-- ------------------------------------------------------------
INSERT INTO spots (code, type, status, plate) VALUES
    ('A-001', 'NORMAL',     'FREE', NULL),
    ('A-002', 'NORMAL',     'FREE', NULL),
    ('A-003', 'NORMAL',     'FREE', NULL),
    ('A-004', 'NORMAL',     'FREE', NULL),
    ('B-001', 'ACCESSIBLE', 'FREE', NULL),
    ('B-002', 'ACCESSIBLE', 'FREE', NULL),
    ('C-001', 'CHARGING',   'FREE', NULL);

-- ------------------------------------------------------------
-- 月卡：一张有效、一张已过期
--   · 京A12345  有效期 2027-12-31  → 有效
--   · 京B00001  有效期 2024-01-01  → 已过期（用于验证 BUG-S4）
-- ------------------------------------------------------------
INSERT INTO month_cards (plate, valid_until, issued_at) VALUES
    ('京A12345', '2027-12-31', '2026-01-01 09:00:00'),
    ('京B00001', '2024-01-01', '2023-01-01 09:00:00');

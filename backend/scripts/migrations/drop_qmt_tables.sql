-- 删除 miniQMT 实盘通道遗留表
--
-- 背景：miniQMT/xtquant 实盘通道已按监管要求下线，相关代码与模型已删除，
-- 这两张表不再有任何读写方。
--
-- 注意：本脚本为破坏性 DDL，禁止接入任何服务启动流程，必须由运维手动执行：
--   psql "$DATABASE_URL" -f backend/scripts/migrations/drop_qmt_tables.sql
--
-- 执行前请确认已完成数据备份（如需保留历史绑定/会话记录）。

BEGIN;

DROP TABLE IF EXISTS qmt_agent_sessions;
DROP TABLE IF EXISTS qmt_agent_bindings;

COMMIT;

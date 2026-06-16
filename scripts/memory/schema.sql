-- ============================================================
--  soul-companion v3.1 - 长期记忆数据库 schema
-- ============================================================
--  两层存储：
--    1. facts   - 结构化事实（用户画像、偏好、关系、关键日期）
--    2. episodes - 情景记忆（对话片段、情绪标记、重要性）
--    3. meta    - 元数据（最后清理时间、配置等）
-- ============================================================

-- ---------- 结构化事实 ----------
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT    NOT NULL,  -- personal|preference|relationship|event|health|work
    key         TEXT    NOT NULL,  -- 字段名，如 birthday / favorite_food / partner_name
    value       TEXT    NOT NULL,  -- 字段值
    confidence  REAL    NOT NULL DEFAULT 1.0,  -- 0-1，1.0=用户明确说，<1=推测
    source      TEXT    NOT NULL DEFAULT 'user_explicit',  -- user_explicit|inferred|imported
    importance  REAL    NOT NULL DEFAULT 0.5,   -- 0-1，越高越不容易被遗忘
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(category, key)
);

CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_importance ON facts(importance);
CREATE INDEX IF NOT EXISTS idx_facts_updated_at ON facts(updated_at);

-- ---------- 情景记忆 ----------
CREATE TABLE IF NOT EXISTS episodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,            -- 会话 ID（同一话题聚合）
    role          TEXT    NOT NULL,  -- user|assistant|system
    content       TEXT    NOT NULL,
    emotion       TEXT,            -- neutral|sad|anxious|excited|angry|grateful|lonely
    importance    REAL    NOT NULL DEFAULT 0.5,
    embedding_id  INTEGER,         -- 指向 vector_index 的 ID（可选）
    tags          TEXT,            -- JSON 数组 ["妈妈", "工作压力", "生日"]
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    last_accessed TEXT,
    access_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_episodes_emotion ON episodes(emotion);
CREATE INDEX IF NOT EXISTS idx_episodes_importance ON episodes(importance);
CREATE INDEX IF NOT EXISTS idx_episodes_created_at ON episodes(created_at);

-- ---------- 元数据 ----------
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------- 触发器：自动更新 updated_at ----------
CREATE TRIGGER IF NOT EXISTS trg_facts_updated_at
AFTER UPDATE ON facts
FOR EACH ROW
BEGIN
    UPDATE facts SET updated_at = datetime('now') WHERE id = OLD.id;
END;

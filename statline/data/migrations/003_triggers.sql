-- 003_triggers.sql
PRAGMA foreign_keys = ON;

-- guild_config
CREATE TRIGGER IF NOT EXISTS trg_gconfig_set_ts
AFTER INSERT ON guild_config
FOR EACH ROW
WHEN NEW.created_ts IS NULL OR NEW.updated_ts IS NULL
BEGIN
  UPDATE guild_config
    SET created_ts = COALESCE(NEW.created_ts, CAST(strftime('%s','now') AS INTEGER)),
        updated_ts = COALESCE(NEW.updated_ts, CAST(strftime('%s','now') AS INTEGER))
    WHERE guild_id = NEW.guild_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_gconfig_touch
BEFORE UPDATE ON guild_config
FOR EACH ROW
BEGIN
  SET NEW.updated_ts = CAST(strftime('%s','now') AS INTEGER);
END;

-- Repeat similar triggers for players, teams, guild_max_stats if desired.

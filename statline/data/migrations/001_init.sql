PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS guild_config (
  guild_id            TEXT PRIMARY KEY,
  sheet_key           TEXT NOT NULL,
  sheet_tab           TEXT DEFAULT 'MAX_STATS',
  last_sync_ts        INTEGER DEFAULT 0,
  last_forced_update  INTEGER DEFAULT 0,
  rate_limit_day      TEXT DEFAULT NULL,  -- prefer NULL over ''
  created_ts          INTEGER NOT NULL,
  updated_ts          INTEGER NOT NULL
) WITHOUT ROWID /* STRICT */;

CREATE TABLE IF NOT EXISTS teams (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id    TEXT NOT NULL,
  team_name   TEXT NOT NULL,
  wins        INTEGER DEFAULT 0 CHECK (wins >= 0),
  losses      INTEGER DEFAULT 0 CHECK (losses >= 0),
  UNIQUE (guild_id, team_name),
  FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
) /* STRICT */;

CREATE TABLE IF NOT EXISTS players (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id     TEXT NOT NULL,
  display_name TEXT NOT NULL,  -- canonical name
  fuzzy_key    TEXT NOT NULL,  -- consider GENERATED ALWAYS AS (lower(display_name)) STORED
  team_name    TEXT,
  -- cached per-game stats (last synced)
  ppg REAL DEFAULT 0 CHECK (ppg >= 0),
  apg REAL DEFAULT 0 CHECK (apg >= 0),
  orpg REAL DEFAULT 0 CHECK (orpg >= 0),
  drpg REAL DEFAULT 0 CHECK (drpg >= 0),
  spg REAL DEFAULT 0 CHECK (spg >= 0),
  bpg REAL DEFAULT 0 CHECK (bpg >= 0),
  fgm REAL DEFAULT 0 CHECK (fgm >= 0),
  fga REAL DEFAULT 0 CHECK (fga >= 0),
  tov REAL DEFAULT 0 CHECK (tov >= 0),
  UNIQUE (guild_id, fuzzy_key),
  FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
) /* STRICT */;

-- Per-guild "max stats" payload (JSON). One row per guild.
CREATE TABLE IF NOT EXISTS guild_max_stats (
  guild_id    TEXT PRIMARY KEY
              REFERENCES guild_config(guild_id) ON DELETE CASCADE,
  stats_json  TEXT NOT NULL
              CHECK (json_valid(stats_json)),   -- requires JSON1
  created_ts  INTEGER NOT NULL,
  updated_ts  INTEGER NOT NULL
) WITHOUT ROWID /* STRICT */;

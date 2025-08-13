PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS guild_config (
  guild_id            TEXT PRIMARY KEY,
  sheet_key           TEXT NOT NULL,
  sheet_tab           TEXT DEFAULT 'MAX_STATS',
  last_sync_ts        INTEGER DEFAULT 0,
  last_forced_update  INTEGER DEFAULT 0,
  rate_limit_day      TEXT DEFAULT '',  -- YYYY-MM-DD the last forced /update day
  created_ts          INTEGER NOT NULL,
  updated_ts          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id    TEXT NOT NULL,
  team_name   TEXT NOT NULL,
  wins        INTEGER DEFAULT 0,
  losses      INTEGER DEFAULT 0,
  UNIQUE (guild_id, team_name),
  FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS players (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id     TEXT NOT NULL,
  display_name TEXT NOT NULL,  -- canonical name
  fuzzy_key    TEXT NOT NULL,  -- lowercased/normalized
  team_name    TEXT,
  -- cached per-game stats (last synced)
  ppg REAL DEFAULT 0, apg REAL DEFAULT 0, orpg REAL DEFAULT 0, drpg REAL DEFAULT 0,
  spg REAL DEFAULT 0, bpg REAL DEFAULT 0, fgm REAL DEFAULT 0, fga REAL DEFAULT 0, tov REAL DEFAULT 0,
  UNIQUE (guild_id, fuzzy_key),
  FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
);

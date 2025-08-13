CREATE INDEX IF NOT EXISTS idx_players_guild_fuzzy ON players (guild_id, fuzzy_key);
CREATE INDEX IF NOT EXISTS idx_teams_guild_name ON teams (guild_id, team_name);

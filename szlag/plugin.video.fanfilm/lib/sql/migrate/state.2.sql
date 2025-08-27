BEGIN;

DROP TABLE IF EXISTS media_base_info;
ALTER TABLE trakt_playback RENAME COLUMN tv_dbid TO main_dbid;

UPDATE trakt_playback SET main_dbid = dbid WHERE type = 'movie';
UPDATE trakt_playback SET season = -1 WHERE season IS NULL;
UPDATE trakt_playback SET episode = -1 WHERE episode IS NULL;
UPDATE trakt_playback SET type = 'show' WHERE season != -1;

-- ALTER COLUMN doesn't exist in sqlite3, than have not to add "NOT NULL"

COMMIT;

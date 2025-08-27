-- Migrate to playback.db version 2.

BEGIN;

DROP TABLE IF EXISTS trakt_playback;

COMMIT;

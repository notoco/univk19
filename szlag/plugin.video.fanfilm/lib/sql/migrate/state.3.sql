BEGIN;

DROP TABLE IF EXISTS access;

ALTER TABLE trakt_playback RENAME TO old_trakt_playback;

CREATE TABLE IF NOT EXISTS "trakt_playback" (
	"id" INTEGER PRIMARY KEY DEFAULT NULL,
	"xref::type" TEXT NOT NULL,
	"xref::dbid" INTEGER NOT NULL,
	"xref::season" INTEGER NOT NULL DEFAULT -1,
	"xref::episode" INTEGER NOT NULL DEFAULT -1,
	"dbid" INTEGER NOT NULL DEFAULT 0,
	"tmdb" INTEGER DEFAULT NULL,
	"imdb" TEXT DEFAULT NULL,
	"trakt" INTEGER DEFAULT NULL,
	"tvdb" INTEGER DEFAULT NULL,
	"slug" TEXT DEFAULT NULL,
	"tv_slug" TEXT DEFAULT NULL,
	"playback_id" INTEGER DEFAULT NULL,
	"progress" REAL DEFAULT NULL,
	"progress_map" TEXT DEFAULT NULL,
	"paused_at" INTEGER DEFAULT NULL,
	"play_count" INTEGER DEFAULT NULL,
	"last_watched_at" INTEGER DEFAULT NULL,
	"duration" INTEGER DEFAULT NULL,
	"aired_at" INTEGER DEFAULT NULL,
	"next_aired_at" INTEGER DEFAULT NULL
	"meta_updated_at" INTEGER DEFAULT NULL,
	UNIQUE("xref::type", "xref::dbid", "xref::season", "xref::episode"));

ALTER TABLE old_trakt_playback RENAME COLUMN "type" TO "xref::type";
ALTER TABLE old_trakt_playback RENAME COLUMN "main_dbid" TO "xref::dbid";
ALTER TABLE old_trakt_playback RENAME COLUMN "season" TO "xref::season";
ALTER TABLE old_trakt_playback RENAME COLUMN "episode" TO "xref::episode";

INSERT INTO trakt_playback SELECT id, "xref::type", "xref::dbid", "xref::season", "xref::episode", dbid, tmdb, imdb, trakt, tvdb, slug, tv_slug, playback_id, progress, paused_at, play_count, last_watched_at, duration, aired_at, meta_updated_at FROM old_trakt_playback;
DROP TABLE old_trakt_playback;

COMMIT;

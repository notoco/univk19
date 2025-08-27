BEGIN;

ALTER TABLE trakt_playback RENAME COLUMN "xref::dbid" TO "xref::ffid";
ALTER TABLE trakt_playback RENAME COLUMN "dbid" TO "ffid";

COMMIT;

BEGIN;

ALTER TABLE directory_content RENAME COLUMN "xref::dbid" TO "xref::ffid";

COMMIT;

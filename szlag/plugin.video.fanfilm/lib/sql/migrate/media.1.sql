BEGIN;

DELETE FROM db WHERE ROWID > 1;

ALTER TABLE info RENAME COLUMN "dbid" TO "ffid";
ALTER TABLE info RENAME COLUMN "main_dbid" TO "main_ffid";

ALTER TABLE ref_list_items RENAME COLUMN "dbid" TO "ffid";

COMMIT;

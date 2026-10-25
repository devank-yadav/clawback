-- Google Drive document versions (api/drive.py): one row per version of a file brought in from the supplier's
-- shared folder, by its sha256. Old versions are kept and never edited. Safe to run again.

CREATE TABLE IF NOT EXISTS document_versions (
    account_id     text NOT NULL,
    doc_id         text NOT NULL,              -- the document's id in the account ("amendment-1", "drive-peak-bar-…")
    version        integer NOT NULL,           -- 1, 2, … in the order Drive changed it
    sha256         text NOT NULL,
    drive_file_id  text NOT NULL,
    name           text NOT NULL,              -- the file's name in Drive
    kind           text NOT NULL,              -- deals | notices | remittances | sales (its folder)
    modified_time  text,                       -- Drive's modifiedTime
    seen_at        timestamptz NOT NULL,
    PRIMARY KEY (account_id, doc_id, version)
);
CREATE INDEX IF NOT EXISTS document_versions_file ON document_versions (drive_file_id);

CREATE TABLE upload_usage (
 user_id TEXT NOT NULL REFERENCES users(id), day TEXT NOT NULL, pages INTEGER NOT NULL CHECK(pages>=0),
 PRIMARY KEY(user_id,day)
);
CREATE INDEX upload_usage_day ON upload_usage(day);
CREATE TABLE job_metrics (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, outcome TEXT NOT NULL,
 duration_ms INTEGER NOT NULL CHECK(duration_ms>=0), created_at TEXT NOT NULL
);
CREATE INDEX job_metrics_created ON job_metrics(created_at);

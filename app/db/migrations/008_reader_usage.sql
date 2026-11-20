CREATE TABLE question_usage (
 user_id TEXT NOT NULL REFERENCES users(id), day TEXT NOT NULL,
 count INTEGER NOT NULL CHECK(count>=0), PRIMARY KEY(user_id,day)
);
CREATE INDEX question_usage_day ON question_usage(day);

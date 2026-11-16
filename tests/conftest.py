import pytest

from app.db.connection import Database
from app.db.migrate import migrate


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "db.sqlite3")
    migrate(db)
    return db


@pytest.fixture
def seeded(database):
    with database.write_tx() as conn:
        conn.execute(
            "INSERT INTO users VALUES ('u','owner@example.test',NULL,'user','2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO documents VALUES ('d','u','Synthetic','sha','synthetic','[\"en\"]',1,'ready','2027-01-01','2026-01-01','2026-01-01',NULL)"
        )
        conn.execute("INSERT INTO revisions VALUES ('d',1,'initial',NULL,'2026-01-01','u')")
        conn.execute("INSERT INTO pages VALUES ('p','d',0,'iii',100,100,0,NULL,'[1,0,0,1,0,0]')")
        conn.execute(
            "INSERT INTO blocks VALUES ('b','d','p','paragraph',NULL,1,'[0,0,1,1]','Synthetic text','Synthetic text','en',1,'ok','{}','{}',0,'[]')"
        )
        conn.execute(
            "INSERT INTO block_versions VALUES ('b',1,1,'Synthetic text','[]','u','2026-01-01')"
        )
        conn.execute("INSERT INTO manifests VALUES ('m','d',1,1,'{}','sha','2026-01-01')")
    return database

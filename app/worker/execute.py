import sys

from app.config import load_settings
from app.db.connection import Database
from app.db.repos.jobs import get_job
from app.worker.runner import execute_claimed


def main() -> None:
    settings = load_settings()
    assert settings.pathya_db_path is not None
    database = Database(settings.pathya_db_path)
    with database.read_conn() as connection:
        job = get_job(connection, sys.argv[1])
    if job is None or job["lease_owner"] != sys.argv[2]:
        return
    execute_claimed(database, settings, job)


if __name__ == "__main__":
    main()

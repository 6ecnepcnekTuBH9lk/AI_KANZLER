from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_database(settings):
    (settings.data_dir / "database").mkdir(parents=True, exist_ok=True)
    sqlite = settings.database_url.startswith("sqlite:")
    engine = create_engine(
        settings.database_url, connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {}
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    return engine, sessionmaker(engine, expire_on_commit=False)

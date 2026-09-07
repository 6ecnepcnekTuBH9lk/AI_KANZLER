from alembic import context
from app.core.config import Settings
from app.core.database import Base, make_database
from app.shared import models  # noqa: F401

target_metadata = Base.metadata
if context.is_offline_mode():
    context.configure(
        url=Settings.from_env().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:

    def migrate(connection):
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()

    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        migrate(supplied)
    else:
        engine, _ = make_database(Settings.from_env())
        with engine.connect() as connection:
            migrate(connection)

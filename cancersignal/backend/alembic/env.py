from alembic import context
from pgvector.sqlalchemy import Vector

from app import models  # noqa: F401 -- register all tables
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine


def include_object(obj, name, type_, reflected, compare_to):
    # Preserve existing tables that are not managed by this application's metadata.
    return not (type_ == "table" and reflected and compare_to is None)


def render_item(type_, obj, autogen_context):
    if type_ == "type" and isinstance(obj, Vector):
        return f"Vector({obj.dim})"
    return False


def run_migrations():
    options = dict(target_metadata=Base.metadata, compare_type=True,
                   include_object=include_object, render_item=render_item)
    if context.is_offline_mode():
        context.configure(url=get_settings().database_url, literal_binds=True, **options)
        with context.begin_transaction():
            context.run_migrations()
    else:
        supplied_connection = context.config.attributes.get("connection")
        if supplied_connection is not None:
            context.configure(connection=supplied_connection, **options)
            with context.begin_transaction():
                context.run_migrations()
            return
        with get_engine().connect() as connection:
            context.configure(connection=connection, **options)
            with context.begin_transaction():
                context.run_migrations()


run_migrations()

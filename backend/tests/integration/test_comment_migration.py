"""RED tests for Alembic 020 article-comment schema migration."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect

def _load_migration():
    migration_path = Path(__file__).parents[2] / "migrations" / "versions" / "020_article_comments.py"
    spec = importlib.util.spec_from_file_location("migration_020", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_comment_migration_revises_019_and_declares_expected_revision():
    migration = _load_migration()
    assert migration.revision == "020"
    assert migration.down_revision == "019"


def test_comment_migration_declares_comment_tables_and_indexes():
    migration = _load_migration()
    assert migration.COMMENT_TABLES == {
        "article_comments",
        "comment_likes",
        "comment_actions",
    }
    assert "ix_article_comments_public_order" in migration.INDEX_NAMES
    assert "uq_comment_likes_comment_user" in migration.CONSTRAINT_NAMES


def test_comment_migration_round_trip_creates_and_drops_schema(tmp_path):
    migration = _load_migration()
    engine = create_engine(f"sqlite:///{tmp_path / 'comments.db'}")
    metadata = MetaData()
    for table_name in ("articles", "users", "admin_accounts"):
        Table(table_name, metadata, Column("id", Integer, primary_key=True),
              Column("name", String(100), nullable=True))

    with engine.begin() as connection:
        metadata.create_all(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert {"article_comments", "comment_likes", "comment_actions"} <= {
            table_name for table_name in inspect(connection).get_table_names()
        }
        migration.downgrade()
        assert not (set(inspect(connection).get_table_names()) & migration.COMMENT_TABLES)

    engine.dispose()

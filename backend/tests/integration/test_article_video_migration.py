"""Exercise only revision 023 on an isolated database, never a configured remote."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_023_upgrade_existing_article_constraints_and_downgrade(tmp_path):
    path = Path(__file__).resolve().parents[2] / "migrations/versions/023_article_videos.py"
    spec = importlib.util.spec_from_file_location("article_video_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "022"
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE admin_accounts (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE articles (id INTEGER PRIMARY KEY, title VARCHAR(200))"
        )
        connection.exec_driver_sql("INSERT INTO articles VALUES (1, '旧文章')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert (
            connection.exec_driver_sql("SELECT video_id FROM articles WHERE id=1").scalar() is None
        )
        inspector = sa.inspect(connection)
        assert any(
            item["constrained_columns"] == ["video_id"]
            for item in inspector.get_foreign_keys("articles")
        )
        assert any(
            item["column_names"] == ["video_id"]
            for item in inspector.get_unique_constraints("articles")
        )
        assert any(
            item["column_names"] == ["upload_session_id"]
            for item in inspector.get_unique_constraints("article_videos")
        )
        assert any(
            item["column_names"] == ["file_id"]
            for item in inspector.get_unique_constraints("article_videos")
        )
        assert {"ix_article_videos_cleanup"} <= {
            item["name"] for item in inspector.get_indexes("article_videos")
        }
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert (
            connection.exec_driver_sql("SELECT title FROM articles WHERE id=1").scalar() == "旧文章"
        )
        assert "article_videos" not in sa.inspect(connection).get_table_names()
        assert "video_id" not in {
            item["name"] for item in sa.inspect(connection).get_columns("articles")
        }
    engine.dispose()

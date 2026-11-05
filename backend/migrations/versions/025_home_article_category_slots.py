"""Bind four existing article category IDs to Mini Program home sections.

Revision ID: 025
Revises: 024
"""

import sqlalchemy as sa
from alembic import op


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


HOME_CATEGORY_IDS = (
    (4, "about"),
    (3, "wellness"),
    (2, "women"),
    (5, "articles"),
)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "article_categories" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("article_categories")}
    if "home_section_key" not in columns:
        op.add_column(
            "article_categories",
            sa.Column("home_section_key", sa.String(length=24), nullable=True),
        )

    unique_names = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints("article_categories")
    }
    if "uq_article_categories_home_section_key" not in unique_names:
        op.create_unique_constraint(
            "uq_article_categories_home_section_key",
            "article_categories",
            ["home_section_key"],
        )

    categories = sa.table(
        "article_categories",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String(length=50)),
        sa.column("home_section_key", sa.String(length=24)),
    )
    if "articles" in tables:
        articles = sa.table(
            "articles",
            sa.column("category", sa.String(length=50)),
            sa.column("category_id", sa.Integer()),
        )
    else:
        articles = None

    for category_id, section_key in HOME_CATEGORY_IDS:
        category_name = bind.execute(
            sa.select(categories.c.name).where(categories.c.id == category_id)
        ).scalar()
        if category_name is None:
            raise RuntimeError(
                f"Home article category ID {category_id} is missing; "
                "refusing to bind the wrong category to a home section"
            )

        bind.execute(
            categories.update()
            .where(categories.c.id == category_id)
            .values(home_section_key=section_key)
        )
        if articles is not None:
            bind.execute(
                articles.update()
                .where(
                    articles.c.category_id.is_(None),
                    articles.c.category == category_name,
                )
                .values(category_id=category_id)
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "article_categories" not in set(inspector.get_table_names()):
        return

    unique_names = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints("article_categories")
    }
    if "uq_article_categories_home_section_key" in unique_names:
        op.drop_constraint(
            "uq_article_categories_home_section_key",
            "article_categories",
            type_="unique",
        )

    columns = {column["name"] for column in inspector.get_columns("article_categories")}
    if "home_section_key" in columns:
        op.drop_column("article_categories", "home_section_key")

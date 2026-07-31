# Data Model: 文章管理增强

**Feature**: 003-article-editor-cos | **Date**: 2026-07-31

## New Entity: ArticleCategory

**Table**: `article_categories`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | INT PK | AUTO_INCREMENT | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | 分类名称 |
| `sort_order` | INT | NOT NULL, DEFAULT 0 | 排序序号，越小越前 |
| `created_at` | DATETIME | NOT NULL | |

## Modified Entity: Article

**Table**: `articles` — Add column:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `category_id` | INT FK → article_categories.id | NULLABLE, ON DELETE SET NULL | 关联分类 |

Existing `category` (VARCHAR) and `category_label` (VARCHAR) columns are retained for backward compatibility; migration populates them from the FK on read, and new writes set `category_id` only.

## Relationships

```
ArticleCategory (1) ──→ (N) Article
```

## Seed Data

Default category created on startup:
- `name`: "默认分类"
- `sort_order`: 0

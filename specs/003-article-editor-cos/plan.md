# Implementation Plan: 文章管理增强

**Branch**: `003-article-editor-cos` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-article-editor-cos/spec.md`

## Summary

增强文章管理模块：新增分类管理（CRUD+排序+删除保护）、集成Quill富文本编辑器（支持图片上传至腾讯云COS）、提供文章预览功能。后端新增ArticleCategory模型和分类CRUD API，将COS客户端改造为支持通用前缀参数化。

## Technical Context

**Language/Version**: Python 3.12 (backend), JavaScript/Vue 3 (frontend)
**Primary Dependencies**: FastAPI + SQLAlchemy (backend), Vue 3 + Quill + Element Plus (frontend)
**Storage**: MySQL 8.0 (categories), 腾讯云COS (article images)
**Target Platform**: Web browser (admin SPA), Linux server (backend API)
**Project Type**: Web application (frontend SPA + backend REST API)
**Performance Goals**: 图片上传 < 5s, 分类列表 < 200ms
**Constraints**: COS上传由后端代理生成预签名URL, 前端不持有COS凭证
**Scale/Scope**: 分类 < 100, 文章 < 10K, 单图 < 10MB

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. TDD | ✅ | 分类CRUD和COS接口先写测试 |
| II. API-First | ✅ | 分类API + 图片上传API契约先行 |
| III. Separation of Concerns | ✅ | manageSystem/ + backend/ 分层 |
| IV. Database Integrity | ✅ | category_id FK via Alembic migration |
| V. Simplicity (YAGNI) | ✅ | 复用COS客户端参数化, 不引入重型CMS |

## Project Structure

### Documentation

```text
specs/003-article-editor-cos/
├── plan.md / research.md / data-model.md / quickstart.md
└── contracts/articles.md
```

### Source Code

```text
backend/src/
├── models/
│   ├── article.py           # ADD: category_id FK + relationship
│   └── category.py          # NEW: ArticleCategory model
├── api/v1/
│   ├── admin_articles.py    # UPDATE: add category_id to CRUD
│   ├── admin_categories.py  # NEW: category CRUD endpoints
│   └── cos_upload.py        # NEW: article image upload endpoint
└── integrations/
    └── cos_client.py        # UPDATE: parameterize key_prefix

manageSystem/src/
├── pages/articles/
│   ├── index.vue            # UPDATE: category filter column
│   ├── editor.vue           # UPDATE: Quill editor + image upload
│   ├── preview.vue          # NEW: article preview page
│   └── categories.vue       # NEW: category management page
├── components/
│   └── ArticleEditor.vue    # NEW: Quill wrapper with COS image handler
└── stores/
    ├── articles.js          # UPDATE: fix data unwrap + category methods
    └── categories.js        # NEW: category CRUD store
```

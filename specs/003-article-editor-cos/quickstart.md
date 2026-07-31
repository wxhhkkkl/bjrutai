# Quickstart: 文章管理增强

**Feature**: 003-article-editor-cos | **Date**: 2026-07-31

## Prerequisites

- COS Bucket (`bjrutai-uploads`) with public-read or pre-signed URL access
- COS credentials in backend `.env` (COS_SECRET_ID, COS_SECRET_KEY, COS_BUCKET, COS_REGION)

## Backend

```bash
cd backend
alembic upgrade head   # adds category_id FK + article_categories table
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend

```bash
cd manageSystem
npm install @vueup/vue-quill quill
npm run dev
```

## Verification

1. 进入文章管理 → 分类管理 → 新建"政策解读"分类
2. 新建文章 → 选择分类 → Quill编辑器输入内容 → 上传图片 → 保存
3. 文章列表按分类筛选
4. 点击预览 → 新标签页查看文章渲染效果
5. 删除未使用分类 → 成功; 删除已使用分类 → 提示错误

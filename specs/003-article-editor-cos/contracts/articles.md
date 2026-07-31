# API Contracts: 文章管理增强

**Feature**: 003-article-editor-cos | **Date**: 2026-07-31

All endpoints under `/api/v1`. Unified response `{code, message, data, requestId, serverTime}`.

## Categories (`/admin/categories`)

### GET — List categories
**Response**: `{data: {items: [{id, name, sort_order, created_at}]}}` ordered by sort_order ASC.

### POST — Create
**Request**: `{name: str, sort_order?: int}`
**Validation**: name unique, max 50 chars.

### PUT /{id} — Update
**Request**: `{name?: str, sort_order?: int}`

### DELETE /{id} — Delete
**Pre-check**: If articles reference this category → 409 with count. Otherwise delete.

---

## Article Image Upload (`/admin/articles/upload-image`)

### POST — Get upload URL
**Request**: `{fileName: str, contentType: str}` (e.g., `image/png`)
**Response**: `{data: {uploadUrl, fileUrl, expiresAt}}`

Flow:
1. Frontend sends fileName + contentType to backend
2. Backend validates (type in jpg/png/gif/webp, extension matches)
3. Backend generates COS pre-signed PUT URL (10min TTL, key: `articles/YYYY/MM/{uuid}.{ext}`)
4. Frontend PUTs file directly to `uploadUrl`
5. Frontend inserts `fileUrl` into editor

---

## Modified: Articles CRUD (`/admin/articles`)

### POST — Create (update existing)
Add `category_id?: int` to request body.

### PUT /{id} — Update (update existing)
Add `category_id?: int` to request body.

### GET — List (update existing)
Add `category_id?: int` query filter. Response items include `category_id` and `category_name`.

---

## Preview (`/articles/{id}`)

### GET — Get article for preview
Returns article detail with rendered HTML content. Public (no admin auth required for preview).
**Response**: `{data: {id, title, category_name, content (HTML), author_name, published_at}}`

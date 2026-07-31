# Tasks: 文章管理增强 — 分类、编辑器、COS上传、预览

**Input**: Design documents from `/specs/003-article-editor-cos/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/articles.md

**Tests**: Included per constitution Principle I (TDD).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no dependencies)
- **[Story]**: US1=分类管理, US2=编辑器+COS, US3=文章预览

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare dependencies and shared backend changes

- [ ] T001 [P] Install @vueup/vue-quill and quill packages in manageSystem/ (npm install)
- [ ] T002 [P] Create ArticleCategory model with id/name/sort_order/created_at in backend/src/models/category.py
- [ ] T003 Generate Alembic migration: add article_categories table + category_id FK to articles in backend/migrations/
- [ ] T004 [P] Refactor COSClient.generate_upload_token to accept optional key_prefix parameter (default "qualifications/") in backend/src/integrations/cos_client.py
- [ ] T005 [P] Update COSClient allowed content types: add image/gif and image/webp in backend/src/integrations/cos_client.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend category CRUD + COS upload API — required by all user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 [P] Write test: category CRUD (create, list, update, delete, delete-protected) in backend/tests/contract/test_categories.py
- [ ] T007 [P] Write test: article image upload token returns valid presigned URL in backend/tests/contract/test_cos_upload.py
- [ ] T008 Create admin_categories.py: GET/POST/PUT/DELETE endpoints at /admin/categories in backend/src/api/v1/admin_categories.py
- [ ] T009 Create cos_upload.py: POST /admin/articles/upload-image endpoint (validate type/size, return presigned URL) in backend/src/api/v1/cos_upload.py
- [ ] T010 Register category and cos_upload routers in backend/src/main.py
- [ ] T011 Update admin_articles.py: add category_id to ArticleCreate/ArticleUpdate schemas and CRUD operations in backend/src/api/v1/admin_articles.py
- [ ] T012 Update admin_articles.py GET list: add category_id query filter + include category_name in response items in backend/src/api/v1/admin_articles.py
- [ ] T013 Create categories Pinia store (fetch, create, update, delete) in manageSystem/src/stores/categories.js

**Checkpoint**: Backend APIs ready — categories CRUD, COS upload token, articles support category_id

---

## Phase 3: User Story 1 - 文章分类管理 (Priority: P1) 🎯 MVP

**Goal**: Admin can CRUD article categories with sort ordering, assign category when editing articles, filter articles by category

**Independent Test**: Create categories → assign to article → filter list by category → delete unused category → delete assigned category shows error

### Implementation

- [ ] T014 [US1] Create categories.vue: category list table (name, sort_order, article count, created_at) in manageSystem/src/pages/articles/categories.vue
- [ ] T015 [US1] Build create/edit category dialog (name input + sort_order number) in manageSystem/src/pages/articles/categories.vue
- [ ] T016 [US1] Build delete category with confirmation + error handling (assigned articles check) in manageSystem/src/pages/articles/categories.vue
- [ ] T017 [US1] Update articles/index.vue: add category filter dropdown above table in manageSystem/src/pages/articles/index.vue
- [ ] T018 [US1] Update articles/index.vue: show category name column in article list table in manageSystem/src/pages/articles/index.vue
- [ ] T019 [US1] Update articles/editor.vue: add category select dropdown (from categories store) in manageSystem/src/pages/articles/editor.vue
- [ ] T020 [US1] Add route for /articles/categories in manageSystem/src/router/index.js

**Checkpoint**: Category management fully functional — list, create, edit, delete with protection, article filtering

---

## Phase 4: User Story 2 - 富文本编辑器与COS上传 (Priority: P1)

**Goal**: Article editor uses Quill WYSIWYG with image upload to COS, paste filtering

**Independent Test**: Create article → type formatted text → upload image via toolbar → image appears in editor → save → reopen → content and images load correctly

### Tests

- [ ] T021 [P] [US2] Write test: upload-image endpoint validates file type and returns presigned URL in backend/tests/contract/test_cos_upload.py
- [ ] T022 [P] [US2] Write component test: ArticleEditor renders Quill toolbar in manageSystem/tests/components/ArticleEditor.test.js

### Implementation

- [ ] T023 [US2] Create ArticleEditor.vue: Quill wrapper component with custom image handler (upload → COS → insert) in manageSystem/src/components/ArticleEditor.vue
- [ ] T024 [US2] Configure Quill toolbar: bold, italic, H1-H3, ul, ol, link, image in manageSystem/src/components/ArticleEditor.vue
- [ ] T025 [US2] Implement COS image upload flow in ArticleEditor: select file → POST /admin/articles/upload-image → PUT to presigned URL → insert returned fileUrl in manageSystem/src/components/ArticleEditor.vue
- [ ] T026 [US2] Add file validation in ArticleEditor: reject non-image files, enforce 10MB limit with user-facing error messages in manageSystem/src/components/ArticleEditor.vue
- [ ] T027 [US2] Update articles/editor.vue: replace textarea with ArticleEditor component, bind content v-model in manageSystem/src/pages/articles/editor.vue
- [ ] T028 [US2] Add paste handler: Quill's built-in sanitizer strips script/iframe/on* attributes in manageSystem/src/components/ArticleEditor.vue

**Checkpoint**: Rich text editing works — formatting, image upload to COS, content save/load, paste filter

---

## Phase 5: User Story 3 - 文章预览 (Priority: P2)

**Goal**: Admin can preview article as it will appear to end users in a new tab

**Independent Test**: Edit article → click Preview → new tab shows rendered article → close tab → edit state preserved

### Implementation

- [ ] T029 [US3] Add preview API: GET /articles/{id} returns rendered article detail (public, no auth required) in backend/src/api/v1/app.py (or new endpoint)
- [ ] T030 [US3] Create preview.vue: page rendering article title, category badge, author, publish date, and content HTML (v-html) in manageSystem/src/pages/articles/preview.vue
- [ ] T031 [US3] Add route /articles/preview/:id in manageSystem/src/router/index.js
- [ ] T032 [US3] Add "预览" button in editor.vue that opens preview in new tab: window.open('/articles/preview/' + articleId) in manageSystem/src/pages/articles/editor.vue

**Checkpoint**: Preview works — new tab shows full article rendering with images

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: Integration validation and default data

- [ ] T033 Add "默认分类" seed data in seed_service.py (idempotent, created on startup if no categories exist) in backend/src/services/seed_service.py
- [ ] T034 [P] Run backend tests: `cd backend && pytest tests/contract/test_categories.py tests/contract/test_cos_upload.py -v`
- [ ] T035 [P] Run quickstart.md verification: create category → edit article with Quill → upload image → preview → filter by category

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1): No deps → can start immediately
- Foundational (Phase 2): Depends on Phase 1 → BLOCKS all user stories
- US1 (Phase 3): Depends on Phase 2
- US2 (Phase 4): Depends on Phase 2 (can parallel with US1)
- US3 (Phase 5): Depends on Phase 2 + editor (T027) from US2
- Polish (Phase 6): Depends on all user stories

### Parallel Opportunities

- Phase 1: T001 ∥ T002 ∥ T004 ∥ T005
- Phase 2: T006 ∥ T007, T008 ∥ T009
- After Phase 2: US1 and US2 can run in parallel
- Phase 4: T021 ∥ T022 can run in parallel

### MVP Scope

Phase 1 + Phase 2 + Phase 3 (US1) = Category management usable.
Add Phase 4 (US2) = Full article editing with images.

---

## Notes

- [P] tasks = different files, no dependencies
- Constitution Principle I (TDD) enforced for backend tests
- COS upload uses existing presigned URL pattern (no new COS SDK)
- Article Editor reuses Quill's built-in clipboard sanitizer

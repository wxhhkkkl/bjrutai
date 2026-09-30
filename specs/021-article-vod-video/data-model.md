# Data Model: 文章视频

**Feature**: `021-article-vod-video` | **Date**: 2026-09-29

## Relationship

```text
articles (existing)
  video_id NULL ───────► article_videos.id
                           1 row = 1 authorized VOD upload attempt
```

`articles.video_id` is nullable and unique. A video can be the current video of at most one article; an article has at most one current video. Old and canceled uploads remain in `article_videos` temporarily for reconciliation and safe cleanup. The specification's conceptual `VideoUploadSession` is represented by the session fields of `article_videos`, not a second table.

## New table: `article_videos`

| Field | Type | Constraint / purpose |
|---|---|---|
| `id` | INT | Primary key; returned to admin as `videoId` |
| `upload_session_id` | VARCHAR(36) | Unique random UUID; embedded in VOD `sourceContext` and `sessionContext` |
| `uploaded_by_admin_id` | INT | FK to `admin_accounts.id`; records who requested authorization |
| `file_name` | VARCHAR(255) | Display only; never used as cloud path |
| `content_type` | VARCHAR(50) | Allowed MIME for MP4/MOV |
| `declared_size_bytes` | BIGINT | Client-declared size, must be `> 0` and `<= 1,073,741,824` |
| `actual_size_bytes` | BIGINT NULL | Verified from VOD media metadata; required before `ready` |
| `vod_sub_app_id` | BIGINT | Configured VOD application ID, server assigned |
| `file_id` | VARCHAR(100) NULL | Unique VOD `FileId`; set only after trusted event correlation |
| `procedure_task_id` | VARCHAR(255) NULL | Processing task from VOD event, for diagnostics |
| `status` | ENUM | `authorized`, `processing`, `ready`, `failed`, `deleting`, `deleted` |
| `upload_confirmed_at` | DATETIME NULL | Trusted VOD event or independent cloud query confirms upload completion |
| `processing_confirmed_at` | DATETIME NULL | Required task flow completed successfully |
| `playback_url` | VARCHAR(2048) NULL | Verified HTTPS MP4 output URL; public only when `ready` |
| `poster_url` | VARCHAR(2048) NULL | Optional VOD snapshot; article cover is fallback |
| `duration_seconds` | FLOAT NULL | Optional, nonnegative media duration |
| `failure_message` | VARCHAR(255) NULL | Sanitized user-facing failure; never raw cloud exceptions |
| `ownership_verified` | BOOLEAN | Cloud metadata proves the application upload context; required for cleanup |
| `unbound_at` | DATETIME NULL | When no article currently references this row; starts at creation |
| `cloud_deleted_at` | DATETIME NULL | Successful VOD deletion time |
| `created_at`, `updated_at` | DATETIME | UTC audit times |

Indexes: unique `upload_session_id`, unique nullable `file_id`, index `(status, unbound_at)` for cleanup, unique nullable `articles.video_id`. The foreign key from `articles.video_id` to `article_videos.id` uses `RESTRICT` on video deletion so a referenced record cannot disappear by accident.

## Existing table change: `articles`

| Field | Change |
|---|---|
| `video_id` | Nullable INT FK to `article_videos.id`, unique. `NULL` for all existing articles. |

Migration: `backend/migrations/versions/023_article_videos.py`, with `down_revision = "022"`. Create `article_videos`, add `articles.video_id`, constraints and indexes. Downgrade removes the article FK/column before dropping the table; downgrade is destructive to newly uploaded video metadata and requires an explicit rollback decision in deployment.

## State and invariants

```text
authorized ── trusted NewFileUpload ──► processing
processing ── successful task + verified media ──► ready
authorized/processing ── invalid/failed/expired ──► failed
unbound ready/failed ── cleanup claim ──► deleting ──► deleted
```

- A `ready` video requires matching upload and processing confirmations, a unique `FileId`, verified `actual_size_bytes <= 1 GB`, and an HTTPS MP4 URL under the configured VOD playback host.
- If the processing event arrives first, store its correlated result but do not mark `ready` until an upload event or independent cloud query confirms the same session and `FileId`. Duplicate events are idempotent; a stale failure cannot roll back a confirmed newer result.
- `Article.status = published` and `Article.video_id != NULL` requires the referenced video to be `ready` at publish time and on every published video switch. Drafts may reference `authorized` or `processing` videos.
- When a video is detached or its article is deleted, set `unbound_at`. When attached, clear it. First binding requires a server-created upload session owned by the acting administrator; a draft may bind it while `authorized` or `processing`, and a published article requires `ready`.
- Public serialization includes video only when the article is published and its current video is `ready`. Historical articles have `video = null` without data migration.
- Cleanup selects only records created by this feature and unbound for at least 7 days. It checks the absence of an `articles.video_id` reference while atomically claiming the row as `deleting`, then calls VOD `DeleteMedia` outside the database transaction; new attachments reject `deleting` media. A cloud failure leaves the record retryable and does not erase evidence of the attempt.

## Concurrency

`Article.version` remains the optimistic lock for create/edit workflows, but the existing read-then-compare code must be strengthened with a row lock or a conditional `UPDATE ... WHERE version = expectedVersion`. Updating title/body and switching `video_id` occurs in one transaction. If two admins edit from the same version, the later write returns conflict and does not detach the previous video. Callback transactions lock or conditionally update the video row; they never write `articles.video_id` directly. Cleanup claims use conditional state changes so concurrent workers cannot delete the same asset twice.

Implementation uses INT identifiers to match existing article/admin identifiers. VOD callbacks are independently checked with `DescribeMediaInfos` and `DescribeTaskDetail`. Status refresh reconciles a known upload/task after 60 seconds without an update, so missing notifications can recover without trusting browser FileId/URLs. A never-confirmed upload expires after 24 hours. Cleanup has a durable 15-minute retry claim and is disabled until `VOD_CLEANUP_ENABLED=true`.

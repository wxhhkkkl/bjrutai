# API Contract: 文章点播视频

**Feature**: `021-article-vod-video` | **Base path**: `/api/v1` | **Date**: 2026-09-29

Business APIs retain the existing envelope `{code, message, data, requestId, serverTime}`. Article IDs and video IDs are decimal strings in JSON. Existing article request/response fields remain valid; `videoId` and `video` are additive.

## 1. Request upload authorization

`POST /admin/article-videos/uploads` — admin JWT + `articles.write`

```json
{
  "fileName": "health-intro.mov",
  "contentType": "video/quicktime",
  "sizeBytes": 734003200
}
```

Success `201`:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "videoId": "37",
    "status": "authorized",
    "uploadSignature": "<short-lived VOD client signature>",
    "expiresAt": "2026-09-29T12:30:00Z"
  },
  "requestId": "...",
  "serverTime": "2026-09-29T11:30:00Z"
}
```

Validation: basename only, MP4/MOV extension and matching MIME, `0 < sizeBytes <= 1,073,741,824`. Backend creates a random session ID and issues a one-hour, one-time VOD signature scoped to the configured application, procedure, `sourceContext` and `sessionContext`. The response never contains `SecretKey`; Tencent's standard encoded signature includes the identifying `secretId`, with no separate credential fields returned. Upload progress remains a browser SDK event, not a server field.

## 2. Read server-confirmed video state

`GET /admin/article-videos/{videoId}` — admin JWT + `articles.write`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "videoId": "37",
    "fileName": "health-intro.mov",
    "status": "processing",
    "playbackUrl": null,
    "posterUrl": null,
    "durationSeconds": null,
    "message": "视频处理中"
  },
  "requestId": "...",
  "serverTime": "..."
}
```

Possible statuses: `authorized`, `processing`, `ready`, `failed`, `deleting`, `deleted`. A `ready` response includes the verified HTTPS `playbackUrl`; a failed response includes a sanitized reason. The form polls while `authorized` or `processing`, and stops on `ready` or `failed`. The uploader or an administrator editing the article currently bound to the video may read its status; unrelated uploads return `404` to avoid revealing another upload.

## 3. Attach, replace, or remove on article writes

Existing `POST /admin/articles` accepts optional `videoId` (positive decimal string or `null`). Existing `PUT /admin/articles/{articleId}` accepts the same field with these semantics:

| `videoId` in PUT | Meaning |
|---|---|
| Absent | Keep current video |
| `null` | Remove current video on successful save |
| Positive decimal string | Set current video on successful save |

Example update:

```json
{
  "title": "健康科普",
  "version": 4,
  "videoId": "37"
}
```

The backend validates the media was authorized by this application, belongs to the initiating admin for first binding, is not attached to another article, and is not deleting/deleted. Draft create/update may reference `authorized` or `processing` media. If the article is already published, a new `videoId` must be `ready`; otherwise return `409` and keep the previous article/version/video unchanged. A stale article `version` also returns `409`. The video relationship changes in the same transaction as the article edit. Existing article write authentication stays in place; any request that adds or changes `videoId` additionally requires `articles.write`.

Existing `POST /admin/articles/{articleId}/publish` returns `409` if the article references a video that is not `ready`. Publishing an article with `videoId = null` remains valid. Unpublish behavior is unchanged.

Admin article list items add:

```json
"video": {
  "videoId": "37",
  "fileName": "health-intro.mov",
  "status": "ready",
  "playbackUrl": "https://vod.example.cn/path/video.mp4",
  "posterUrl": "https://vod.example.cn/path/poster.jpg",
  "durationSeconds": 86.4
}
```

`video` is `null` when there is no current video. Admin serialization may show the state of a draft's pending video; it must not fabricate a playback URL before `ready`.

## 4. Published article detail

Existing `GET /articles/{articleId}` adds only an optional `video` object:

```json
"video": {
  "playbackUrl": "https://vod.example.cn/path/video.mp4",
  "posterUrl": "https://vod.example.cn/path/poster.jpg",
  "durationSeconds": 86.4
}
```

`video` is `null` for no video or a current video that is no longer `ready`. All existing title/content/cover/comment fields and published-only `404` behavior stay unchanged. The public list response need not include video. The client treats an absent `video` property as `null` for compatibility with older servers.

## 5. Tencent VOD event receiver

`POST /integrations/tencent-vod/events` — no admin JWT; HTTPS callback only

The request body is Tencent VOD's `NewFileUpload` or `ProcedureStateChanged` event. It includes `Sign = MD5(SignKey + T)`, where `T` is the signature expiry Unix timestamp. The endpoint validates this signature and expiry, correlates `FileUploadEvent.MediaBasicInfo.SourceInfo.SourceContext` / `ProcedureStateChangeEvent.SessionContext` to the upload row, and queries cloud metadata plus task details to verify matching `FileId`, application, task and completion status. Only verified H.264/AAC HTTPS MP4 output permits `ready`. Unknown authenticated sessions are acknowledged without creating media records. Invalid signature or expired timestamp returns `401`; malformed events return `400`. Successful and duplicate events return HTTP `200` after committing the state.

The callback may arrive before the SDK's `done()` response, after the admin leaves the page, or out of order. The server state is authoritative in all cases. Status refresh reconciles known media/tasks after 60 seconds without a state update. A never-confirmed session expires after 24 hours. No raw callback body, media signature, or cloud credential is stored in logs. Browser retries use fresh sessions with SDK resume disabled, so a cached cloud session cannot mismatch the new server authorization.

## Error classes

| HTTP | Situation | Client behavior |
|---|---|---|
| 400 / 422 | Invalid type, name, size or payload | Show field-specific validation |
| 401 / 403 | Missing/expired admin login or `articles.write` | Reauthenticate or show no permission |
| 404 | Article/video absent or inaccessible | Refresh list/edit form |
| 409 | Article version conflict, video not ready/claimed | Keep edit state, refresh server status |
| 503 | VOD signing/metadata service unavailable | Explain temporary failure and allow retry |

All business errors use the existing response envelope and do not expose VOD secrets or raw cloud error bodies.

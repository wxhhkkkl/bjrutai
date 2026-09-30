# Implementation Plan: 文章视频上传与小程序点播

**Branch**: `021-article-vod-video` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/021-article-vod-video/spec.md`

## Summary

在现有文章管理表单增加可选单视频上传，管理后台使用腾讯云点播 Web SDK 直传，后端派发短期签名并依据点播事件确认上传、转码及播放地址。新增 `article_videos` 表与 `articles.video_id`，草稿可保留处理中的视频，发布与已发布文章换片只接受就绪视频。公开文章详情以兼容字段返回 HTTPS MP4 地址，小程序文章详情在正文上方使用原生视频组件播放。视频失效只影响视频区块，图文仍可阅读。

## Technical Context

**Language/Version**: Python 3.11+；JavaScript（Vue 3.5、微信小程序原生 JavaScript）

**Primary Dependencies**: FastAPI、SQLAlchemy 2 async、Pydantic v2、Alembic、腾讯云 API 3.0 Python 点播 SDK；Vue 3、Element Plus、Pinia、Axios、腾讯云点播 Web 上传 SDK；微信小程序原生 `video`

**Storage**: 腾讯云 MySQL 8.0 保存文章与媒资元数据；腾讯云点播保存视频源文件和处理产物；现有 COS 继续保存图片

**Testing**: 后端 pytest/pytest-asyncio 契约、单元和集成测试；管理端 Vitest/Vue Test Utils；小程序现有 Node 测试及 iOS/Android 微信真机验收

**Target Platform**: Linux 后端、现代桌面浏览器管理后台、微信小程序

**Project Type**: Web API + 管理后台 SPA + 微信小程序

**Performance Goals**: 上传签名与视频状态接口正常网络下 p95 < 500 ms（不含云服务故障）；视频文件不流经后端；详情接口增加视频字段后保持现有响应级别

**Constraints**: 每篇文章最多 1 个视频；MP4/MOV、每文件不超过 1 GB；小程序只播放已发布文章的就绪视频；播放 URL 必须为配置域名上的 HTTPS MP4；服务端不暴露长期云密钥

**Scale/Scope**: 一张新媒资表、一列文章外键、约 3 组新后端接口/回调、现有文章 CRUD 扩展、一个后台编辑区块、现有小程序文章详情扩展

## Constitution Check

*GATE: 已在设计前检查，并在数据模型和契约完成后复核。*

| Principle | Pre-design | Post-design | Evidence |
|---|---|---|---|
| I. Test-Driven Development | PASS | PASS | 实施阶段先写上传授权、回调、状态、发布、替换、公开详情和小程序播放的失败测试，再实现功能；本 `plan` 阶段不写生产代码。 |
| II. API-First Design | PASS | PASS | [API contract](./contracts/api.md) 先定义统一响应、视频关联语义、回调与错误状态；前端只消费后端文章/视频 API。 |
| III. Separation of Concerns | PASS | PASS | 后端负责签名、权限、云状态验证、文章关联与清理；管理端负责选择文件/进度/预览；小程序负责展示与播放。 |
| IV. Database Integrity | PASS | PASS | `023` Alembic 迁移、外键/唯一约束和事务保护；云密钥环境变量配置；前端不连接数据库或获取长期凭证。 |
| V. Simplicity (YAGNI) | PASS | PASS | 复用现有文章路由、版本号、权限、维护任务和小程序详情；单表表示媒资及上传会话；不引入独立视频管理系统、播放器插件或消息队列。 |

Gate status: **PASS**。无宪章违规，无待解决的产品澄清项。腾讯云应用与微信资质属于部署前置核对项。

## Project Structure

### Documentation (this feature)

```text
specs/021-article-vod-video/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api.md
└── tasks.md                 # speckit-tasks 阶段输出
```

### Source Code (repository root)

```text
backend/
├── .env.example
├── requirements.txt
├── migrations/versions/023_article_videos.py
├── src/
│   ├── core/config.py
│   ├── models/{article,article_video,__init__}.py
│   ├── schemas/{article,article_video}.py
│   ├── services/{article_service,article_video_service,tencent_vod,article_video_cleanup}.py
│   ├── api/v1/{admin_articles,article_videos,articles}.py
│   └── main.py
└── tests/
    ├── conftest.py
    ├── contract/test_article_videos.py
    ├── integration/{test_article_video_flow,test_article_video_migration}.py
    └── unit/test_article_video_service.py

manageSystem/
├── package.json / package-lock.json
└── src/
    ├── components/articles/{ArticleEditor,ArticleVideoUpload}.vue
    ├── components/articles/__tests__/{ArticleEditor,ArticleVideoUpload}.spec.js
    ├── api/article-videos.js / api/__tests__/{article-videos,article-preview}.spec.js
    ├── utils/article-preview.js
    └── stores/articles.js

miniProgram/
├── models/article.js
├── pages/article-detail/index.{js,wxml,wxss}
└── tests/
    ├── integration/article-reading-flow.test.js
    └── unit/article-video.test.js
```

**Structure Decision**: 继续使用仓库现有 `backend/`、`manageSystem/`、`miniProgram/` 三层。视频状态与云服务调用集中在后端独立服务，不把 1 GB 文件经现有图片上传路由转发。管理端只新增文章编辑内的上传区块，小程序只改文章详情页。

## Implementation Sequence

1. **锁定契约并先写失败测试**：覆盖上传限制/权限、签名不泄密、回调认证与乱序、转码失败、文章版本冲突、发布门槛、公开详情无视频兼容及小程序播放/失败。确认测试在未实现时失败。
2. **迁移与领域模型**：新增 `023` 迁移、`ArticleVideo` 模型、文章外键/唯一约束及状态转换；既有文章默认 `NULL`。验证迁移升级和回滚定义。
3. **点播集成**：配置最小权限云凭据、应用 ID、任务流、回调密钥与播放域名；后端签发短期上传签名，接收经过验证的云事件，核验文件大小、处理结果和 HTTPS 输出。
4. **文章服务与 API**：在同一事务内验证并设置 `videoId`，为已发布文章保留旧视频直到新视频就绪且保存成功；发布前检查就绪；公开详情只输出可播放视频，其他文章行为保持原样。
5. **管理端交互**：通过 Web SDK 上传并显示进度；轮询后端处理状态；支持草稿待处理、已发布文章替换/移除、失败重试及当前表单预览。清楚区分上传进度和云端处理状态。
6. **小程序播放**：适配可选 `video` 字段；在封面/摘要之后、正文之前加入原生播放器；默认不自动播放，离开/隐藏时暂停，错误可重试，图文不受影响。
7. **媒资清理与发布核对**：复用维护任务扫描超期未绑定媒资，云端删除前重查引用并记录/重试；完成三端测试、迁移检查、构建及真机验收；核对点播配置、HTTPS、微信资质和域名。

## Implementation Design

### Upload and processing flow

管理端先向本站请求授权，后端创建上传记录并签名；浏览器直传 VOD。点播上传完成事件带回 `sourceContext`，任务流完成事件带回 `sessionContext`。后端在同一会话/`FileId` 下确认两类事件，并核查实际大小及转码产物后标记 `ready`。回调重复可安全重试；处理事件先到时先保留结果，上传确认前不开放播放。详见 [research.md](./research.md) 与 [data-model.md](./data-model.md)。

### Article consistency

`Article.video_id` 是唯一当前指针。草稿可以指向待处理视频，但发布时必须就绪；已发布文章换片只在新视频就绪后执行。现有文章服务仅先读取再比较 `Article.version`，实施时须以行锁或带版本条件的更新让版本校验与视频切换原子化，避免并发覆盖。前端未提交的视频不影响读者当前播放；保存成功后下一次公开详情才返回新视频。清理任务只接触没有当前文章引用的本应用上传媒资。

### Playback and failure behavior

公开详情 `video` 为 `null` 或 `{playbackUrl, posterUrl, durationSeconds}`。小程序原生播放器仅使用后端给出的 HTTPS URL；无视频时不渲染播放器。加载失败仅显示视频区块错误，保留标题、正文、图片与评论。页面隐藏和卸载时暂停播放器，避免后台声音。

## Complexity Tracking

无宪章违规，不需要复杂度豁免。

## Implementation notes — 2026-09-29

上传与回调路由共用 `article_videos.py`，云 SDK 适配置于现有 services 目录，清理逻辑独立文件；测试复用仓库现有入口以减少文件分散。媒体和任务均向云端复核，状态刷新可恢复遗漏事件。SDK 跨上传会话的断点缓存关闭，防止新授权错误复用旧上传上下文。详见 `validation.md`；目标 MySQL 并发与云端/真机验收仍待部署阶段。

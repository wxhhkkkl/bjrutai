# Tasks: 文章视频上传与小程序点播

**Input**: Design documents from `/specs/021-article-vod-video/`

**Prerequisites**: `spec.md`、`plan.md`、`research.md`、`data-model.md`、`contracts/api.md`

**Tests**: 仓库宪章要求 TDD。每组生产代码开始前，先编写对应测试并运行确认因目标功能缺失而失败；完成后运行同一组测试使其通过。本次已实施并运行本地自动化检查。测试按仓库现有目录组织；配置测试与状态测试共用服务测试文件。

## Format: `[ID] [P?] [Story] Description`

- `[P]` 表示与同阶段其他任务使用不同文件且无前置依赖，可并行执行。
- `[US1]` 上传并保存视频；`[US2]` 更换、移除与预览；`[US3]` 小程序播放。
- 路径均相对于仓库根目录 `LuTaiMiniProgram/`。

## Phase 1: Setup（依赖与测试入口）

**目标**：准备点播 SDK 与隔离云服务的测试入口，不接触真实云资源。

- [x] T001 [P] 在 `backend/tests/conftest.py` 准备可注入的点播客户端替身、后台有/无 `articles.write` 权限管理员，以及固定的上传/处理事件样本；测试样本不得包含真实密钥。
- [x] T002 [P] 在 `backend/requirements.txt` 添加并固定兼容的腾讯云 API 3.0 Python 公共异步包及 VOD 产品包；在 `manageSystem/package.json` 添加点播 Web 上传 SDK，并更新对应依赖锁文件。
- [x] T003 在 `backend/tests/unit/test_article_video_service.py` 编写并运行失败的配置测试：缺少点播应用 ID、任务流、回调密钥或播放主机时上传授权受控失败，响应与日志不包含长期密钥。

**Checkpoint**：测试环境可替换点播客户端，依赖可安装，配置安全边界已有失败测试。

## Phase 2: Foundational（模型、迁移与状态基础）

**目标**：建立单视频关联和上传会话状态，阻塞所有用户故事的生产实现。

### 先写失败测试

- [x] T004 [P] 在 `backend/tests/integration/test_article_video_migration.py` 编写并运行失败的迁移测试：从修订 `022` 升级到 `023`、存量文章 `video_id=NULL`、外键/唯一约束、索引和降级顺序。
- [x] T005 [P] 在 `backend/tests/unit/test_article_video_service.py` 编写并运行失败的状态测试：授权→处理中→就绪/失败、同一 `FileId` 唯一、重复/乱序通知、未绑定时间和删除占用状态。

### 实现基础能力

- [x] T006 在 `backend/migrations/versions/023_article_videos.py` 建立 `article_videos` 表及 `articles.video_id` 可空唯一外键，`down_revision="022"`；加入上传会话、`FileId` 与清理索引。
- [x] T007 在 `backend/src/models/article_video.py`、`backend/src/models/article.py` 和 `backend/src/models/__init__.py` 定义媒资字段、文章关系与状态，保证 Alembic 可发现模型；在 `backend/src/schemas/article_video.py` 定义上传授权与状态输出 schema。
- [x] T008 在 `backend/.env.example` 和 `backend/src/core/config.py` 加入点播应用 ID、地域、后端密钥、任务流、回调密钥与 HTTPS 播放主机配置；在 `backend/src/services/article_video_service.py` 实现纯状态转换与不变量校验，只有上传确认、处理成功、实际大小合规及 HTTPS MP4 地址均成立时才能进入 `ready`。
- [x] T009 运行 T003–T005 对应测试，确认配置、迁移与状态基础由红转绿，并核查现有图文文章在数据库层无需数据回填。

**Checkpoint**：数据结构支持待绑定上传、每文至多一个当前视频及旧视频延迟清理；没有云服务或前端代码依赖真实密钥。

## Phase 3: User Story 1 - 新建/编辑文章上传视频（Priority: P1）🎯 上传 MVP

**目标**：有权限的管理员可上传 MP4/MOV（≤1 GB），看到进度与真实处理状态，保存含待处理/就绪视频的草稿并重新打开。

**独立验收**：选择视频→直传点播→处理就绪→保存草稿→重新编辑仍显示视频；上传失败和无权限请求得到明确反馈。

### 先写失败测试

- [x] T010 [P] [US1] 在 `backend/tests/contract/test_article_videos.py` 编写并运行失败的授权/状态接口测试：MP4/MOV 与 1 GB 边界、MIME/后缀不符、`articles.write` 拒绝、统一响应、短期签名不泄露密钥及他人上传记录不可读。
- [x] T011 [P] [US1] 在 `backend/tests/unit/test_article_video_service.py` 编写并运行失败的云事件测试：无效签名/过期时间、未知会话、`NewFileUpload` 与 `ProcedureStateChanged` 乱序/重复、实际大小超限、转码失败、非 HTTPS 或非允许域名输出。
- [x] T012 [P] [US1] 在 `backend/tests/integration/test_article_video_flow.py` 编写并运行失败的草稿链路测试：授权上传、可信云事件、创建/编辑草稿绑定、重新读取视频状态、上传取消后无效媒资不能变成可播放视频。
- [x] T013 [P] [US1] 在 `manageSystem/src/components/articles/__tests__/ArticleVideoUpload.spec.js` 编写并运行失败的表单测试：文件限制、SDK 上传进度、处理轮询、失败重试、保存草稿后重新打开，区分“上传完成”和“可播放”；覆盖本地预览、云端地址切换及资源释放。

### 实现

- [x] T014 [US1] 在 `backend/src/services/tencent_vod.py` 实现短期客户端上传签名与官方点播 API 查询适配，签名绑定随机会话、点播应用、任务流及上下文；云 API 调用设定超时并隐藏敏感错误。
- [x] T015 [US1] 在 `backend/src/services/article_video_service.py` 实现授权创建、格式/大小/归属校验、上传完成与任务流事件摄取、媒资元信息核验和幂等状态更新。
- [x] T016 [US1] 在 `backend/src/api/v1/article_videos.py` 实现 `POST /admin/article-videos/uploads`、`GET /admin/article-videos/{videoId}`；在 `backend/src/api/v1/article_videos.py` 实现经过 `SignKey`/时间校验的点播回调，并在 `backend/src/main.py` 注册路由。
- [x] T017 [US1] 在 `backend/src/schemas/article.py`、`backend/src/services/article_service.py`、`backend/src/api/v1/admin_articles.py` 增加草稿创建/编辑的 `videoId` 绑定和后台文章视频输出；首次绑定验证上传者、应用和占用关系，视频关系与文章数据在同一事务保存。
- [x] T018 [US1] 在 `manageSystem/src/components/articles/ArticleVideoUpload.vue` 接入点播 Web SDK 的选择、直传、进度、取消、状态轮询及本地文件预览；云端就绪或编辑已有视频时使用可信播放地址，切换/移除/关闭时释放本地 URL。在 `manageSystem/src/components/articles/ArticleEditor.vue`、`manageSystem/src/stores/articles.js` 接入可选视频及草稿保存/回填，失败时保留既有图文输入。
- [x] T019 [US1] 运行 T010–T013 的后端和管理端测试，使上传草稿链路由红转绿；按 US1 独立验收复查无权限、失败、重新打开场景。

**Checkpoint**：管理员能独立完成上传并保存含视频草稿；视频未就绪时界面如实显示状态。尚未开放已发布文章换片与小程序播放。

## Phase 4: User Story 2 - 更换、移除与预览文章视频（Priority: P1）

**目标**：已发布文章在新视频就绪且保存前继续使用原视频，移除与预览正确展示；并发编辑不会覆盖他人的视频关系。

**独立验收**：对已发布文章上传新视频，处理中公开详情仍指向原视频；就绪并保存后切换；移除后保留图文；过期版本保存被拒绝。

### 先写失败测试

- [x] T020 [P] [US2] 在 `backend/tests/contract/test_article_videos.py` 编写并运行失败的文章写入契约测试：`videoId` 缺省/`null`/字符串语义、处理中视频阻止发布和已发布文章换片、无写权限、视频被占用、统一 `409` 错误。
- [ ] T021 [P] [US2] 在 `backend/tests/integration/test_article_video_flow.py` 编写并运行失败的事务测试：旧视频保持到保存成功、并发相同 `version` 仅一方成功、移除/文章删除标记旧视频未绑定、失败保存不改变旧引用。
- [x] T022 [P] [US2] 在 `manageSystem/src/components/articles/__tests__/ArticleVideoUpload.spec.js` 编写并运行失败的编辑测试：处理中不能把新视频保存到已发布文章、就绪后换片、移除确认、当前表单预览视频顺序及关闭预览后输入保留。

### 实现

- [x] T023 [US2] 在 `backend/src/services/article_service.py` 对文章更新使用行锁或带版本条件的更新，使版本检查、视频归属/就绪检查、指针切换及旧视频 `unbound_at` 更新成为原子操作；发布前拒绝未就绪视频，删除文章时保留媒资清理记录。
- [x] T024 [US2] 在 `backend/src/api/v1/admin_articles.py` 和 `backend/src/schemas/article.py` 完成已发布文章换片、移除、发布校验的错误与响应契约；只有视频关联变更请求增加 `articles.write` 服务端权限校验，保持无视频请求兼容。
- [x] T025 [US2] 在 `manageSystem/src/components/articles/ArticleEditor.vue`、`manageSystem/src/components/articles/ArticleVideoUpload.vue` 实现已发布文章更换/移除状态及当前表单的视频预览；替换现有拼接 `document.write` 的预览方式，避免执行文章中的脚本。
- [x] T026 [US2] 运行 T020–T022 对应测试并独立验收已发布换片、移除、预览和版本冲突；确认原文章内容与封面未被视频操作清空。

**Checkpoint**：已发布文章的视频变更具备原子性，读者在编辑期间始终能得到已保存的可播放版本。

## Phase 5: User Story 3 - 小程序文章详情播放视频（Priority: P1）

**目标**：已发布且就绪的视频显示在摘要之后、正文之前；读者可播放、暂停、拖动与全屏，错误局部重试，无视频文章保持原样。

**独立验收**：使用含封面/摘要/视频/正文的已发布文章，iOS 与 Android 微信真机播放；验证无视频、失效视频、草稿/下架和页面隐藏场景。

### 先写失败测试

- [x] T027 [P] [US3] 在 `backend/tests/contract/test_articles.py` 编写并运行失败的公开详情契约测试：只为已发布且 `ready` 视频返回可选 `video`，不返回草稿/下架媒体；存量无视频详情兼容，公开列表契约不变。
- [x] T028 [P] [US3] 在 `miniProgram/tests/unit/article.test.js`、`miniProgram/tests/unit/article-video.test.js` 编写并运行失败的适配测试：可选视频字段、HTTPS/域名异常、海报回退、无视频与旧版服务端响应。
- [x] T029 [P] [US3] 在 `miniProgram/tests/integration/article-reading-flow.test.js` 编写并运行失败的详情流程测试：播放器位置、默认不自动播放、隐藏/卸载暂停、播放失败局部重试、视频独立于正文/评论错误。

### 实现

- [x] T030 [US3] 在 `backend/src/services/article_service.py`、`backend/src/api/v1/articles.py` 加入公开详情的可选视频序列化，只有当前媒资 `ready` 且 URL 合规时返回播放信息；不改变现有文章列表、浏览量和发布过滤。
- [x] T031 [US3] 在 `miniProgram/models/article.js` 适配 `video` 或缺失字段，校验播放 URL 并为海报使用视频截图或文章封面；避免让富文本解析器处理视频标签。
- [x] T032 [US3] 在 `miniProgram/pages/article-detail/index.wxml`、`index.wxss` 添加独立原生 `video` 区块，保持竖屏/横屏比例和底部分享条空间；视频文章即使正文为空也不显示误导性的空正文占位。
- [x] T033 [US3] 在 `miniProgram/pages/article-detail/index.js` 管理播放器上下文、错误/重试与 `onHide`/`onUnload` 暂停；播放异常不得清除已加载的文章、图片或评论。
- [x] T034 [US3] 运行 T027–T029 对应测试，并按 US3 独立验收文章有视频、无视频、播放失败及页面退出行为。

**Checkpoint**：三条 P1 用户故事均可独立验收；文章读者可在小程序播放点播视频。

## Phase 6: Polish & Cross-Cutting Validation

- [x] T035 [P] 在 `backend/tests/unit/test_article_video_service.py`、`backend/tests/integration/test_article_video_flow.py` 先编写并运行失败的未绑定媒资清理测试：满 7 天才入候选、被文章引用永不删除、并发只领取一次、云端删除失败可重试。
- [x] T036 在 `backend/src/services/article_video_service.py` 实现超期未绑定媒资的原子领取、引用复核与点播 `DeleteMedia`；在 `backend/src/services/article_video_cleanup.py` 和 `backend/src/main.py` 注册维护任务，记录不含密钥/签名的结果，运行 T035 使之通过。
- [x] T037 [P] 在 `backend/tests/contract/test_article_videos.py`、`manageSystem/src/components/articles/__tests__/ArticleVideoUpload.spec.js` 检查敏感信息边界：长期密钥不进入响应、日志或前端包；回调伪造/重放拒绝，表单错误不暴露云端原始异常。
- [x] T038 运行 `specs/021-article-vod-video/quickstart.md` 列出的后端、管理端、小程序针对性测试和构建，验证 `023` 迁移升级/回滚定义以及存量图文文章回归。
- [ ] T039 在受控联调环境核对点播应用、任务流、HTTPS 播放域名、回调可达性、最小权限密钥与微信视频相关资质；用 MP4/MOV 样本和 iOS/Android 微信真机完成播放验收，并记录未通过项。

## Dependencies & Execution Order

### Phase dependencies

- Phase 1 无前置依赖；T001–T003 可在不同文件分别准备测试入口、依赖及配置失败测试。
- Phase 2 依赖 Phase 1；T004–T005 必须先失败，再做 T006–T008；Phase 2 完成前不进入用户故事生产实现。
- US1 依赖 Phase 2；先完成可信上传和草稿关联。
- US2 依赖 US1 的上传、媒资状态与文章当前视频关联；可独立验收换片/移除，但不能在基础能力缺失时实施。
- US3 依赖公开详情能够读取 `ready` 视频；其小程序测试和页面工作可与 US2 非共享文件工作并行，完整验收依赖 US1/US2 的服务端契约。
- Phase 6 依赖主要故事完成；清理测试可在 US1 的媒资模型稳定后提前编写。

### Parallel opportunities

- T001 与 T002 文件互不冲突；T004 与 T005 测试文件不同。
- US1 的后端契约、集成测试和管理端测试可并行编写；T014–T018 按服务→API→页面的依赖实施。
- US2 后端契约、集成测试与管理端组件测试可并行；T023–T025 依赖其失败测试。
- US3 后端公开契约、小程序模型契约和小程序页面流程测试可并行；T030–T033 依赖相应失败测试。

## Implementation Strategy

1. **上传 MVP**：Phase 1–3 完成后，管理员可保存带视频的草稿并看到真实处理状态。
2. **安全发布**：Phase 4 完成后，视频就绪门槛、原子换片、移除与预览可独立验收。
3. **读者播放**：Phase 5 完成后，小程序从已发布文章获得视频并播放。
4. **完成条件**：Phase 6 完成后，三端针对性回归、迁移与真机验收通过；云端配置和微信资质在实际发布前核实。

所有测试任务先红后绿。每个用户故事完成时可作一次逻辑检查点提交；是否推送、合并或发布由后续实施请求决定。

## Implementation status — 2026-09-29

代码与本地自动化检查已完成。管理端表单测试另见 `manageSystem/src/components/articles/__tests__/ArticleEditor.spec.js`；视频验证与预览测试见 `manageSystem/src/api/__tests__/article-videos.spec.js` 和 `article-preview.spec.js`。

T021 的旧视频保留、移除、删除及过期版本拒绝已由隔离数据库测试验证，目标 MySQL 上双管理员并发验证待部署验收，因此保留未勾选。目标 MySQL 已升级到迁移 `023`，真实 MP4 上传和回调已通过临时 HTTPS 转发验证；T039 中 MOV、微信 iOS/Android 真机播放、生产部署和权限复核仍待验收。具体执行结果见 `validation.md`。

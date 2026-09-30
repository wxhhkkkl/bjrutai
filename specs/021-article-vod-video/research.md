# Research: 文章视频上传与小程序点播

**Date**: 2026-09-29

**Scope**: `021-article-vod-video`

## Existing System Findings

- `manageSystem/src/components/articles/ArticleEditor.vue` 已提供图文、封面上传、保存草稿与本地预览；没有视频字段。封面经后端 `/admin/articles/upload-image-file` 中转，限制 10 MB，不适合 1 GB 视频。
- `backend/src/models/article.py` 无视频关联。`article_service.py` 负责文章版本控制、发布、公开详情序列化；公开详情只在已发布状态返回。
- `miniProgram/pages/article-detail/index.wxml` 的正文由安全富文本块与图片组成。播放器应作为独立区块插入，避免把 `<video>` 塞入富文本解析器。
- 现有 Alembic 最新修订为 `022`，本功能迁移须接在 `022` 后。后端已有 `articles.write` 权限和 APScheduler 维护任务。

## Decision 1: 浏览器直传云点播

**Chosen**: 管理后台使用腾讯云点播 Web 上传 SDK。后端核验 `articles.write`、文件名/格式/声明大小后创建上传记录，签发短期上传签名；浏览器直接将文件上传到点播。签名包含随机上传会话标识作为 `sourceContext` 和 `sessionContext`，并指定点播应用及处理任务流。SDK 的进度只用于表单即时反馈，完成后的服务端状态以点播事件为准。

**Why**: 用户确认的单文件上限为 1 GB。现有图片中转接口先把整个文件读入后端内存，不能复用；直传避免后端承载视频流量。腾讯云官方 [Web 上传 SDK](https://cloud.tencent.com/document/product/266/9239)支持上传进度、取消与断点续传，[客户端签名](https://cloud.tencent.com/document/product/266/9221)由业务服务端派发，可携带处理任务与上下文。

**Rejected**: 通过 FastAPI 中转文件到点播，会显著增加内存、带宽和超时压力；直接把永久云密钥放入浏览器不符合密钥边界。

## Decision 2: 由点播事件确认媒资归属与就绪

**Chosen**: 配置点播普通 HTTPS 回调，开启上传完成 `NewFileUpload` 与任务流状态变更 `ProcedureStateChanged`。后端验证回调签名及时间、匹配会话上下文与应用 ID、核对 `FileId`，必要时再查点播媒体信息。状态更新以数据库事务和单调状态转换保证幂等；未知会话与重复/过期事件不创建文章关联。管理端轮询本站视频状态接口。

**Why**: SDK 成功回调仅证明浏览器认为上传完成，不足以让客户端任意 `FileId` 成为文章视频。腾讯云[事件通知](https://cloud.tencent.com/document/product/266/33779)支持上传与处理状态；[签名参数](https://cloud.tencent.com/document/product/266/9221)中的 `sourceContext` / `sessionContext` 可分别用于两类事件关联。点播[回调配置](https://cloud.tencent.com/document/api/266/55244)支持 `SignKey` 校验。

**Reliability**: 普通回调有重试机制，但不保证无限重试。后台保留“处理中/异常”状态，超过运维阈值时进行媒资查询与告警，不自动宣称成功。若部署环境无法接受公网 HTTPS 回调，应在实施前切换为腾讯云[可靠回调](https://cloud.tencent.com/document/product/266/33779)消费模式；两种模式只影响事件摄取，不改变文章/API 契约。

**Rejected**: 仅以客户端提交的 `FileId` 或 URL 标记可播放，无法可靠验证上传来源、文件大小及转码结果。此场景先不引入常驻消息队列消费者。

## Decision 3: 云点播处理为兼容小程序的 MP4

**Chosen**: 点播任务流生成 H.264/AAC MP4 播放版本，按需要产出封面截图。只有任务流成功、媒资实际大小不超过 1 GB、播放 URL 为配置域名上的 HTTPS 地址时，视频状态才能进入 `ready`。`MOV` 作为上传源格式，由云端转码供小程序播放。封面缺失时回退到文章封面。

**Why**: 腾讯云[任务流状态通知](https://cloud.tencent.com/document/product/266/9636)提供处理结果、输出 URL 和媒体元信息；[媒体详细信息](https://cloud.tencent.com/document/api/266/31773)提供文件大小、时长与转码地址。腾讯云说明可通过微信原生 `Video` 组件播放点播 URL，但需满足微信端配置及相关资质要求，见[小程序方案](https://cloud.tencent.com/document/product/266/38081)。

**Rejected**: 直接向小程序返回源 MOV 地址，存在端侧兼容性不确定性；引入腾讯播放器插件会增加采购与集成范围，本期原生组件已满足基本播放。

后端媒资查询与删除使用腾讯云官方 [API 3.0 Python SDK](https://github.com/TencentCloud/tencentcloud-sdk-python) 的点播产品包及异步公共包，并固定兼容版本；避免自行实现云 API 请求签名。浏览器上传仍使用独立的 Web 上传 SDK。

## Decision 4: 一个媒资表加文章当前指针

**Chosen**: 增加 `article_videos` 表，每次授权上传对应一行，上传会话信息直接记录在该行；`articles.video_id` 为可空、唯一的当前视频外键。文章更新只切换指针，不覆盖旧媒资行。草稿可指向处理中媒资；已发布文章只能切换到 `ready` 媒资。公开详情仅序列化当前 `ready` 视频。

**Why**: 新建文章时还没有文章 ID，待绑定视频需要独立生命周期；替换已发布文章视频时，旧指针保留到新视频就绪并成功保存。单表承载规格中的 `ArticleVideo` 和概念性 `VideoUploadSession`，避免再建一张会话表。

**Rejected**: 在 `articles` 表直接保存 `fileId`/URL/状态，无法处理新建前上传、替换期间并存的视频，以及未绑定媒资清理。

## Decision 5: 公开播放与媒资生命周期

**Chosen**: 小程序通过公开文章详情取得 HTTPS 播放 URL；不增加播放器签名或防盗链。文章下架后，公开详情不再返回视频，但已取得的公开点播 URL 可能仍可直接访问。这与用户确认的文章公开访问规则一致。仅应用自身授权上传、且已超过 7 天无有效文章引用的媒资进入清理队列；删除前再次检查引用并记录结果，云端删除失败可重试。

**Why**: 本期不包含私密视频授权。腾讯云[删除媒体 API](https://cloud.tencent.com/document/product/266/31764)会删除原视频及处理产物，必须限制在可证明由本应用上传、且未被文章使用的媒资。保留短暂宽限期，避免编辑取消或并发更换时误删。

## Remaining Deployment Checks

1. 确认点播应用 ID、密钥权限、任务流名称、HTTPS 播放域名与回调 `SignKey` 已配置。
2. 确认微信小程序的视频相关类目/资质及播放域名配置满足上线条件；这是上线检查，不由代码推断为已满足。
3. 在目标微信 iOS、Android 真机上核验转码 MP4 的播放、全屏、暂停和海报显示。

# Quickstart: 文章点播视频联调与验收

**Feature**: `021-article-vod-video` | **Date**: 2026-09-29

代码和本地自动化检查已完成，目标 MySQL 已执行迁移 `023`，真实 MP4 上传与处理回调已通过临时 HTTPS 转发联调。生产回调与微信真机播放仍待验收。检查结果见 [validation.md](./validation.md)。

## 1. 云端准备

1. 在腾讯云点播中确认使用的应用 ID，创建或选择可把 MP4/MOV 源文件处理为 H.264/AAC MP4 的任务流；需要视频海报时加入截图任务。
2. 为该应用配置可用的 HTTPS 播放域名，并确认域名与后端允许的播放主机一致。在[默认分发配置](https://cloud.tencent.com/document/product/266/33373)中把主分发协议设为 HTTPS，确保媒体查询返回 HTTPS 地址。
3. 配置上传完成 `NewFileUpload` 和任务流完成 `ProcedureStateChanged` 的普通 HTTPS 回调到 `/api/v1/integrations/tencent-vod/events`，启用回调 `SignKey`。
4. 以最小权限为后端配置点播上传签名、`DescribeMediaInfos`、`DescribeTaskDetail` 和可选 `DeleteMedia` 所需云 API 权限。SecretKey 和回调密钥仅放服务端环境变量。
5. 核对微信小程序的视频类目/资质与播放域名配置。腾讯云[小程序点播说明](https://cloud.tencent.com/document/product/266/38081)指出原生 `Video` 组件可使用点播播放地址，同时需满足微信端要求。

## 2. 后端环境变量

以下变量已加入 `backend/.env.example`；实际值写入部署环境或被忽略的 `backend/.env`：

```dotenv
VOD_SECRET_ID=
VOD_SECRET_KEY=
VOD_SUB_APP_ID=0
VOD_REGION=ap-beijing
VOD_PROCEDURE=
VOD_CALLBACK_SIGN_KEY=
VOD_PLAYBACK_HOSTS=
VOD_CLEANUP_ENABLED=false
```

`VOD_SUB_APP_ID` 填真实数字，`VOD_PROCEDURE` 填已创建的 H.264/AAC MP4 任务流名称。`VOD_PLAYBACK_HOSTS` 填精确主机名，多个用逗号分隔，包含视频与截图使用的主机；不填写协议、路径或通配符。缺少配置时上传接口受控返回 503。

新环境部署前在目标库执行迁移 `023_article_videos.py`（`alembic upgrade head`），之后再启动新后端。本次联调使用的目标 MySQL 已升级至 `023`；升级/降级与存量文章兼容已在隔离 SQLite 验证，目标 MySQL 的并发检查仍待验收。

清理任务默认关闭；确认配置和清理范围后启用 `VOD_CLEANUP_ENABLED=true`。任务每天 03:40 清理满七天的未绑定、归属已验证媒资，云端删除失败可重试。降级到 `022` 会移除新增视频关联与元数据，需先备份这些数据。

## 3. 本地自动化检查

后端（在 `backend/`）：

```sh
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest tests/contract/test_article_videos.py tests/unit/test_article_video_service.py tests/integration/test_article_video_flow.py tests/integration/test_article_video_migration.py tests/contract/test_articles.py tests/integration/test_article_flow.py tests/integration/test_article_cover_upload.py -q
```

管理端（在 `manageSystem/`）：

```sh
npm ci
npx vitest run
npm run build
```

小程序（在 `miniProgram/`）：

```sh
node --test tests/unit/article*.test.js tests/contract/article*.test.js tests/integration/article*.test.js
```

## 4. 云端联调顺序

1. 先用云客户端替身固定上传签名、回调和媒体查询的测试输入，再实现并跑通后端契约/服务测试；测试不得依赖真实云密钥。
2. 完成迁移后，确认存量文章 `video_id` 全部为空，原有公开文章详情仍可被旧小程序客户端读取。
3. 管理端选择小尺寸 MP4，检查上传进度、点播处理中、就绪、保存草稿、重新打开；再用 MOV 验证转码后的小程序播放。
4. 验证错误路径：格式不符、声明大小超限、签名过期、点播处理失败、重复/乱序回调、无权限上传、文章版本冲突。
5. 发布含就绪视频的文章，在 iOS 与 Android 微信真机中检查封面/摘要 → 视频 → 正文顺序、播放/暂停/进度/全屏、页面隐藏暂停、播放失败时图文继续可读。
6. 对已发布文章上传替换视频，确认保存前读者仍收到旧视频；新视频就绪并保存后返回新视频。移除视频后文章图文正常。草稿或下架文章不得经公开详情获得视频。
7. 让取消编辑与替换产生一条未绑定测试媒资，确认清理候选查询只找到无文章引用的本应用媒资；在受控测试环境验证云端删除与失败重试。

## 5. 部署验收检查

- 后端、管理端和小程序的针对性测试及生产构建通过。
- 部署环境未把 VOD 长期密钥、上传签名或回调密钥写入前端产物或日志。
- 点播回调公网 HTTPS 可达，重复通知幂等，处理失败不允许发布。
- 真机可通过 HTTPS 域名播放处理后的 MP4；无视频文章保持原布局。
- 数据库迁移与回滚方案已在测试环境验证，未绑定媒资清理范围经人工核对。

# 文章点播视频实施记录

**日期**：2026-09-30　**分支**：`021-article-vod-video`

## 已实现

- 管理端新建/编辑文章支持一个可选 MP4/MOV 视频，最大 1 GiB；浏览器直传腾讯云点播，展示进度、取消、重新上传和云端状态。首次选择视频立即本地预览；云端就绪及重新编辑时使用播放地址。
- 后端签名、权限、上传会话、媒体归属、实际大小、云端任务及 HTTPS H.264/AAC MP4 输出校验；重复/乱序回调幂等，遗漏处理回调可通过状态查询恢复。
- 草稿可保存待处理上传；发布和已发布文章换片要求就绪；文章版本校验、切换和旧视频解绑在一个事务中完成。
- 视频移除需保存文章才生效；文章图文、封面和评论保留。预览采用禁用脚本的 sandbox iframe 与 CSP。
- 小程序摘要后、正文前使用原生 video，不自动播放；隐藏/退出暂停，播放失败局部重试，无视频文章保持兼容。
- 迁移 `023` 创建媒资表和唯一文章关联，引用中的媒资受 RESTRICT 外键保护。超七天未绑定媒资可清理，默认关闭真实云端清理。

## 主要文件

| 部分 | 文件 |
|---|---|
| 数据与迁移 | `backend/src/models/article_video.py`、`backend/src/models/article.py`、`backend/migrations/versions/023_article_videos.py` |
| 点播 API 与状态 | `backend/src/services/tencent_vod.py`、`article_video_service.py`、`article_video_cleanup.py`、`backend/src/api/v1/article_videos.py` |
| 文章绑定 | `backend/src/services/article_service.py`、`backend/src/api/v1/admin_articles.py`、`backend/src/schemas/article.py` |
| 管理端 | `manageSystem/src/components/articles/ArticleEditor.vue`、`ArticleVideoUpload.vue`、`manageSystem/src/api/article-videos.js`、`manageSystem/src/utils/article-preview.js` |
| 小程序 | `miniProgram/models/article.js`、`miniProgram/pages/article-detail/index.js`、`index.wxml`、`index.wxss` |

## 自动化检查

自动化测试中的云调用使用替身，数据库测试使用隔离 SQLite。另已在目标 MySQL 执行迁移 `023`，并通过临时公网 HTTPS 回调完成真实 MP4 上传与处理联调；没有执行真实点播删除。

- 后端文章视频契约、集成、迁移和服务测试：本次 38 项通过。此前扩大到文章与图片上传相关测试的检查：79 项通过；新增点播服务、清理和接口模块合计覆盖率 84%。
- 管理端 Vitest 全部现有及新增测试：23 项通过。
- 小程序文章视频和阅读流程测试：本次 13 项通过；此前文章与评论相关扩大检查：28 项通过。
- 管理端 Vite 生产构建：通过；官方 SDK 的依赖产生 eval 提醒及大文件提醒，SDK 在选择上传后才加载。
- 新增后端文件 Ruff 检查：通过。

后端测试保留仓库既有 Pydantic、datetime、pytest-asyncio 弃用提醒。

## 待部署验收

以下项目仍待验证：

1. 生产环境公网回调、播放域名与最小权限凭据；临时 HTTPS 转发仅用于本机联调。
2. 目标 MySQL 上双管理员并发编辑；已检查过期版本拒绝、旧引用保留、迁移升级/降级及唯一约束定义。
3. MOV 转码、微信视频相关类目/资质、域名配置和 iOS/Android 真机播放、进度、全屏、暂停。

具体配置和联调步骤见 [quickstart.md](./quickstart.md)。

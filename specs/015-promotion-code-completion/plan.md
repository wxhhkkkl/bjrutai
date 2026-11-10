# Implementation Plan: 我的推广码闭环完善

**Branch**: `015-promotion-code-completion` | **Date**: 2026-08-10 | **Spec**: `spec.md`

## Summary

统一后端推广码响应和小程序消费字段；将页面请求改为顺序加载；实现微信相册保存；拒绝缺少有效令牌的同步自动归属；接通已存在但被页面拦截的客户和资料接口。

## Constitution Check

- 规格先行：通过；本功能的场景、外部依赖和受控失败状态已记录。
- 外部依赖：哈尔滨儒泰负责实际二维码生成与扫码回传，仓库内不虚构其 API。
- 隐私：不记录或显示客户敏感信息；令牌只用于已授权的推广归属。
- 测试：为字段适配、分享路径和无令牌同步补充自动化覆盖。

## Files

- `backend/src/services/promotion_service.py`
- `backend/src/services/sync_service.py`
- `miniProgram/pages/promotion-code/index.js`
- `miniProgram/pages/promotion-code/index.wxml`
- `miniProgram/models/promotion-code.js`
- `miniProgram/pages/customer-detail/index.js`
- `miniProgram/pages/followup-record/index.js`
- `miniProgram/pages/binding-records/index.js`
- `miniProgram/pages/auth/profile-setup/index.js`
- 推广码相关单元与契约测试
- `miniProgram/pages/home/index.{js,wxml,wxss}`
- 首页布局契约测试

## 首页微信分享（2026-11-03 / FR-017）

在首页 Page 中增加 onLoad 分享菜单启用、onShareAppMessage 与 onShareTimeline 回调，使用固定品牌标题与分别适配 5:4 / 1:1 的本地 JPG。封面由内置 imagegen 生成后压缩到分享展示尺寸，保留足够包体余量。不读取个人资料、动态轮播或文章作为分享数据，不新增接口或依赖；验证两种分享返回值、菜单启用、接口失败时稳定性与资源尺寸/体积，并在开发者工具预览卡片。原生分享没有独立 desc 字段，介绍文案在封面呈现。

## 首页分类入口调整（2026-11-03 / FR-015）

仅扩展首页 WXML/WXSS，在轮播与现有内容之间加入提示分割线和四个入口，复用已有跳转处理器。二次视觉调整将 Vant 线框图标替换为四张本地透明立体插画（内置 imagegen 生成），并统一轮播底部、入口区与关于儒泰的背景衔接。生成提示词记录在 `design-assets/home/category-icons-v2-prompts.md`。不新增接口或依赖。验证现有首页导航和布局测试，检查手机宽度下四列尺寸及文字适配；微信真机显示需设备复核。

**2026-11-05 布局修订**：按用户反馈，保留品牌栏，将首屏轮播扩展至 Tab 栏上方；在轮播底部增加“更多精彩请上划”提示，并移除四个分类图标入口区。内容分区及数据、导航逻辑不变。改版前的 WXML、WXSS、JS 和打包配置保存在 `design-assets/home/full-screen-banner-rollback-2026-11-05/`，供演示后回退。

## 延迟登录补绑（2026-11-03 / FR-018～FR-021）

新增 `miniProgram/services/pending-binding-service.js` 保存来源并协调原生确认/补绑；扫码页验证通过后写入，原绑定成功后清除，登录页成功建立会话后及首页 onShow 恢复。App API 环境变化时清除待绑定来源。登录失败和补绑失败分开处理，补绑不得中断正常登录路由。

后端抽取现有 claim 的归属写入逻辑供公开扫码和已登录补绑复用，新接口通过 Bearer 校验当前活跃个人账号，使用服务端手机号，不增加数据库字段/迁移。保留锁定客户行、归属冲突和幂等。先用本地 mocked 页面/服务验证扫码离开、存储、登录确认、失败重试与路由，再使用隔离 SQLite 集成测试验证真实接口与原 claim 回归；运行小程序全套 Node 测试与相关后端测试。符合规格先行、最少数据存储、明确授权和原生组件约束；微信开发者工具/真机可用时验证导航与原生弹窗，否则明确列为未验证。

发布顺序：先部署包含 `claim-session` 的后端，再发布本次小程序；无需数据库迁移。当前仅本地实现和自动化/开发工具编译验证，不改线上数据，不将测试手机号或模拟绑定写入生产。真机扫码、手机号授权及原生弹窗需在发布后用获授权的验收账号验证。

## 我的服务消费入口调整（2026-11-03 / FR-022）

从 app.json 和角色可见 Tab 中移除消费入口；将“我的服务”现有消费卡片改名为“消费记录”，并指向原消费汇总页。该页转为可返回的二级页面，“查看全部”继续打开逐笔列表；保留现有业务能力校验，不改消费 API。

## 互联网医院占位入口（2026-11-03 / FR-023）

复用自定义 Tab，在客户与我的之间注册公开页面 `pages/internet-hospital/index`；使用建筑样式的 Vant `hotel-o` 图标和显示“互联网医院”标题的原生顶部安全区组件。将第二版青绿海报压缩为本地 JPEG，放入完整可见的等比容器，加载失败时展示原生说明文字。检查角色可见导航顺序、Tab 切换、图片加载与 iOS/Android 模拟器适配。选定原图来自本次 imagegen，Canva 设计为 `DAHZ2cA38QM`，核对后无后续修改。

## 客户绑定码分享封面（2026-11-03 / FR-024）

使用内置 imagegen 生成 5:4 青绿品牌邀请封面，压缩为本地 JPEG；原图及提示词放在小程序包外的 design-assets。`createPromotionShare` 返回固定品牌标题及本地封面，保留 API 分享路径和令牌回退路径；朋友圈同步标题，并使用上下留白的 1:1 版本避免裁字。复用并调整现有推广码测试，验证后端路径优先、特殊字符令牌编码和无二维码时封面可用，回归二维码保存。仅修改前端展示，不增加接口或依赖。

## 客户绑定欢迎页（2026-11-04 / FR-025）

从用户选定的设计提取欢迎插画，原生渲染说明和授权按钮。删除页面勾选状态和检查，继续使用微信授权回调和原绑定接口。回归未取得凭证、授权成功、归属冲突与延迟补绑，使用微信开发者工具复核布局。

**2026-11-10 文案修订**：授权页说明改为“点击下方按钮，使用微信授权登录”；只改提示文案，授权与绑定逻辑不变。

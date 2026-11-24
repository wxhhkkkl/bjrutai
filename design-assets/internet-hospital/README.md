# 互联网医院 Tab 页

## 当前页面：复诊患者就诊须知

- 设计源文件：`复诊患者就诊须知_引导图_源文件.html`（用户提供，750px 画布，2026-11-23 归入本目录）。
- 实现页面：`../../miniProgram/pages/internet-hospital/index.wxml` / `index.wxss`，以真实 WXML/WXSS 还原，不使用图片。
- 版式换算：设计稿为 750px 网页画布，按手机宽度重排——页面左右留白 40rpx、卡片圆角 20rpx、内容间距参考设计比例；正文字号按手机可读性放大（正文 28rpx、章节标题 40rpx、主标题 84rpx）。
- 可读性修订：设计稿的辅助文字色 `#8A8479` 在白底上对比度不足，实现改用 `#6F6A60`（约 5:1），其余配色保持设计稿。
- 图标：三个说明图标改用 Vant Weapp 的 `certificate`、`shield-o`、`arrow`，颜色取设计中的金色 `#B08D22`。
- 悬浮按钮：右下角常驻「进入互联网医院」，Tab 同款蓝 `#1677FF` 底 + 白字，固定于 Tab 栏上方 24rpx。点击弹出小程序码弹层，用户长按识别打开目标小程序（`show-menu-by-longpress`）。目标小程序 AppId 为 `wxa60305f071755a87`；因直接调用 `wx.navigateToMiniProgram` 在真机被微信提示「由于小程序违规，该功能暂时无法使用」（实物交易类跳转限制），改用小程序码识别方案。
- 小程序码素材：`../../miniProgram/assets/images/internet-hospital-qrcode.png`（2026-11-24 更新为用户提供的「医宝」小程序码，430×430，JPEG 转 PNG）；加载失败时弹层显示「小程序码暂不可用，请稍后重试」。
- 跳转统计（2026-11-24）：小程序上报 `entry_tap`（已登录点击按钮）和 `qr_longpress`（长按小程序码）；后端接口 `POST /api/v1/hospital/events` 可选登录，事件表 `hospital_visit_events` 只保存用户 ID、事件类型、来源、UTC 时间与上海日期。后台「互联网医院统计」页（权限 `hospital.stats.read`）按日期范围展示总览、按用户与按日明细；用户手机号按 2026-11-24 调整展示原文，仅该权限可见。「按用户统计」支持按当前日期范围导出 Excel（.xlsx，设置列宽、表头加粗、手机号与时间按文本，最多 10000 人，导出写审计日志）。长按只代表「尝试识别」，系统无法确认目标小程序被打开，页面已注明。规格见 `../../specs/023-internet-hospital-stats/spec.md`。

## 已停用的占位图（历史记录）

- 用户选择：本聊天显示的第二张“青绿温暖守护”。
- 生成工具：内置 image_gen；未使用 Canva 重新生成画面。
- 原始图：`selected-original.png`（1024×1536）。
- 小程序素材：原 `../../miniProgram/assets/images/internet-hospital-coming-soon-v1.jpg`（750×1125，JPEG quality 85）；2026-11-23 起页面改为真实内容，占位图已从主包删除。
- Canva 可编辑设计：`DAHZ2cA38QM`；接入前已查询，updated_at 与转换完成时相同，没有后续修改。海报以用户选定原图为视觉基准。
- 调整入口：[Canva 第二版](https://www.canva.com/d/jxkTh-B-YtM0FpB)。Canva 修改不会自动同步小程序，需要重新导出替换本地素材。
- 生成提示词要点：Portrait 1024×1536 placeholder artwork for 儒泰医联 Internet Hospital. Warm ivory base, jade/teal and sage green editorial illustration, delicate paper grain. Friendly adult clinician and family connected through a stylized smartphone with a hospital facade, flowing connection line and restrained botanical leaves. Real blue cross brand logo. Generous whitespace and strong readable Chinese typography. Exact copy: 儒泰医联 / 互联网医院 / 正在建设中 / 我们正在用心完善服务体验 / 敬请期待. No appointment buttons, dates, progress percentages, medical claims, device chrome or navigation tabs.
- 占位图时期的视觉检查（历史）：`preview-comparison.png` 同屏展示等比归一化的原图、Android 实际渲染海报区域与完整 360×640 模拟器页面；原始开发者工具截图为 `android-devtools.png`。这两张图记录的是已停用的占位图，不代表当前页面。

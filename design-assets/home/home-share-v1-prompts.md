# 首页微信分享封面 v1

2026-11-03，使用内置 imagegen 分别生成好友卡片与朋友圈图片；使用系统 sips 缩小并转为 JPEG（质量 85），未改动图中内容。两张最终素材合计约 117 KB，作为本地资源随小程序打包，不依赖图片外链或用户资料。

## 最终文案

- 分享标题：儒泰医联｜让健康知识，走进日常
- 封面主标题：让健康知识 / 走进日常
- 封面介绍：心脑维养 · 女性健康 · 健康资讯
- 品牌：儒泰医联

## 最终素材

- [好友分享封面（500 × 400，5:4）](../../miniProgram/assets/images/home-share-friend-v1.jpg)
- [朋友圈封面（400 × 400，1:1）](../../miniProgram/assets/images/home-share-timeline-v1.jpg)

## 接入

首页 onLoad 启用好友和朋友圈分享菜单；onShareAppMessage 返回固定标题、公开首页路径 /pages/home/index 及好友封面，onShareTimeline 返回相同标题、空 query 及方形封面。分享不附加登录令牌、客户信息或归属参数。接口加载失败也能使用分享；访客打开后沿用现有公开首页。

微信原生分享没有独立 desc 字段，介绍文字直接排在封面中。菜单和返回字段依据 [微信官方 Page 类型说明](https://github.com/wechat-miniprogram/api-typings/blob/master/types/wx/lib.wx.page.d.ts)；图片比例与本地路径使用方式另见 [腾讯云官方分享示例](https://docs.cloudbase.net/recipes/add-share-with-params-miniprogram)。

## 好友封面最终提示词

Use case: ads-marketing. Asset type: final branded image artwork for a WeChat mini-program share card, not an app screenshot. Create a refined, thoughtfully art-directed Chinese health editorial brand image for 儒泰医联. Premium calm healthcare visual language matching deep teal #123f42, porcelain ivory, soft jade and warm brushed gold; one muted coral accent. Soft tactile 3D porcelain and frosted-glass motifs: an open health journal, a gentle heart-and-brain sculpture, and a magnolia blossom with one leaf, composed as one elegant scene on the lower/right side. Mature and polished, restrained details, studio-soft lighting, subtle real shadows, no clutter, no people or doctor portraits. Pale warm-ivory background with a very soft seafoam atmosphere, deep teal typography, high contrast and generous breathing room. Typography must be beautifully typeset simplified Chinese, exact characters, sharply legible. Exact brand text at top: “儒泰医联”. Exact large headline in two lines: “让健康知识” then “走进日常”. Exact smaller descriptor: “心脑维养 · 女性健康 · 健康资讯”. No extra text, no English, no fake brand logos, no QR code, no medical efficacy claims, no promise or call-to-buy. Hierarchy: small brand, large confident headline, restrained descriptor, richly crafted thematic artwork. Keep all text at least 9% away from edges. Canvas MUST be landscape 5:4 aspect ratio, ideally 1280x1024. Editorial composition with typography occupying upper/left 60%, artwork sculptural arrangement mainly lower/right. The main headline should occupy almost half the width, in a modern heavy Chinese sans serif, readable in a 250px-wide WeChat message thumbnail. Text and imagery must not overlap; use a graceful curved jade panel near the lower right edge to ground the objects.

## 朋友圈封面最终提示词

Use case: ads-marketing. Asset type: final branded image artwork for a WeChat mini-program share card, not an app screenshot. Create a refined, thoughtfully art-directed Chinese health editorial brand image for 儒泰医联. Premium calm healthcare visual language matching deep teal #123f42, porcelain ivory, soft jade and warm brushed gold; one muted coral accent. Soft tactile 3D porcelain and frosted-glass motifs: an open health journal, a gentle heart-and-brain sculpture, and a magnolia blossom with one leaf, composed as one elegant scene on the lower/right side. Mature and polished, restrained details, studio-soft lighting, subtle real shadows, no clutter, no people or doctor portraits. Pale warm-ivory background with a very soft seafoam atmosphere, deep teal typography, high contrast and generous breathing room. Typography must be beautifully typeset simplified Chinese, exact characters, sharply legible. Exact brand text at top: “儒泰医联”. Exact large headline in two lines: “让健康知识” then “走进日常”. Exact smaller descriptor: “心脑维养 · 女性健康 · 健康资讯”. No extra text, no English, no fake brand logos, no QR code, no medical efficacy claims, no promise or call-to-buy. Hierarchy: small brand, large confident headline, restrained descriptor, richly crafted thematic artwork. Keep all text at least 9% away from edges. Canvas MUST be square 1:1. This is the companion square thumbnail for WeChat Moments. A centered editorial composition: brand at top, headline centered on the upper half in large modern heavy Chinese sans serif, descriptor immediately below; cohesive 3D journal/heart-brain/magnolia composition on lower half, a light curved jade foundation in the bottom right. All key elements stay in the central 82% safe area. Strong readability when thumbnail is small.

## 验证

分享、公开访问与现有首页共 56 项自动化检查通过。开发者工具已确认“发送给朋友”和“分享到朋友圈”菜单可用，两个预览弹窗显示对应封面与标题；未向真实联系人发送消息或发布朋友圈。真实手机端最终展示和转发仍需复核。

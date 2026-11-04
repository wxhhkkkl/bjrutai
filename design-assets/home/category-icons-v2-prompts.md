# 首页分类插画 v2

2026-11-03，使用内置 imagegen 分别生成四张透明 PNG 插画。接入小程序前用系统 sips 等比例缩小至 320 × 320，保留透明通道；未改动插画内容。四张运行时资源合计约 434 KB。

## 最终文件

- 关于儒泰：[home-category-about-v2.png](../../miniProgram/assets/images/home-category-about-v2.png)
- 心脑维养：[home-category-wellness-v2.png](../../miniProgram/assets/images/home-category-wellness-v2.png)
- 女性专区：[home-category-women-v2.png](../../miniProgram/assets/images/home-category-women-v2.png)
- 健康资讯：[home-category-articles-v2.png](../../miniProgram/assets/images/home-category-articles-v2.png)

## 通用提示词（每张均使用）

Use case: stylized-concept. Asset type: one square image for a WeChat health mini-program category shortcut, one of a coordinated four-image set. Premium crafted 3D editorial illustration, smooth matte porcelain blended with a few softly translucent frosted-glass elements and fine brushed warm-gold accents. Elegant adult healthcare branding, not toy-like, not a generic flat outline icon. Restrained cream, jade/seafoam, pale aqua palette with a little warm coral. Soft studio lighting from upper left, subtle realistic ambient occlusion, crisp clear silhouette, simple enough to recognize at 64px. Three-quarter isometric frontal view, object centered, occupies 80% of square canvas, generous uncut margins. Genuine transparent background, NO tile, NO square/rectangle backdrop, NO text, NO lettering, NO watermark, NO logos. A single cohesive object composition, not a scene, not a contact sheet. Must look beautiful and legible against a deep teal #123f42 app background.

## 关于儒泰

Primary subject: a refined contemporary wellness clinic building with ivory curved facade, seafoam glass windows and entrance, two short architectural wings and a central rounded tower. A small jade plus emblem on its facade, an organic jade leaf curving alongside the building, and a discreet warm gold arc unify the sculpture. Conveys a trustworthy established health organization; architectural details clean and balanced.

## 心脑维养

Primary subject: a smooth warm coral anatomical-inspired heart in the foreground, paired with an elegant seafoam brain slightly behind and above to the right. Both stylized medical forms are immediately recognizable, gentle and non-gory. One graceful mint ECG pulse ribbon connects their base, a fine gold arc encircles part of the composition. Conveys heart and brain maintenance and vitality. No medical tubing or excessive detail.

## 女性专区

Primary subject: an elegant stylized ivory feminine face in side profile, framed by softly sweeping rose-pink hair and a blooming magnolia flower with two jade leaves at the lower side. Sculptural feminine silhouette and expressive petal layers, dignified and graceful, with one fine gold curved accent. Conveys women's health and care, not cosmetics packaging, no bottle, no typography.

## 健康资讯

Primary subject: a beautifully designed small open health journal with ivory dimensional pages, jade cover and gold bookmark, paired with a seafoam frosted-glass magnifier. Pages show a tiny jade plus emblem and two or three abstract embossed lines only, no readable text. One small jade leaf by the spine. Clear sculptural book silhouette, editorial discovery and trustworthy health knowledge.

## 页面接入

入口使用透明插画配浅色分类名称，保持原有跳转。提示文案 28rpx、线条 3rpx；轮播底部渐隐、入口区和关于儒泰共用 #123f42 背景，移除原有 42rpx 浅色间隔。后续按用户首屏示例改为自适应轮播高度，扣除顶部导航、提示、四个入口、底部 Tab 和安全区后分配剩余空间。按最新反馈，图片宽高 100% 并等比铺满，不展示轮播标题。

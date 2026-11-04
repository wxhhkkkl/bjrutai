# 客户绑定码分享封面 v1

用户于 2026-11-03 确认品牌邀请卡方向。使用内置 image_gen 生成，不调用外部 API；原图留在本目录，小程序仅打包压缩后的 JPEG。

- 当前原图：`promotion-share-friend-v2-original.png`，2026-11-04 使用内置 imagegen 删除副标题后替换两种分享封面。
- 初版原图：`promotion-share-friend-v1-original.png`
- 好友封面：`../../miniProgram/assets/images/promotion-share-friend-v1.jpg`，500×400，5:4。
- 朋友圈封面：`../../miniProgram/assets/images/promotion-share-timeline-v1.jpg`，500×500，使用同图上下补米白色留白，保持文字完整。
- 分享标题：儒泰医联｜您的专属健康服务入口。
- 品牌封面不放二维码或用户数据；绑定参数继续取原分享路径；保存按钮继续保存原二维码。

## 初版生成提示词

```text
Use case: ads-marketing. Create a finished raster cover for a WeChat mini program invitation share card for Chinese health service brand 儒泰医联. Exact aspect ratio 5:4 landscape, preferably 1250x1000. It must read beautifully at only 250x200 pixels. This is the image inside the shared card, not a mockup of WeChat: no device frame, chat bubbles or UI chrome.
Style: elegant contemporary editorial illustration, gentle paper texture, restrained sage green, deep teal and warm ivory, generous negative space. Premium, calm, approachable. Simple health service illustration in the lower right: friendly female healthcare adviser holding a teal folder, welcoming gesture, subtle clinic building and a few soft botanical leaves. Keep the illustration sparse, not crowded, no QR code or code patterns, no logo invention, no exaggerated medical promises.
Typography is the priority. Top left small but readable brand text exactly "儒泰医联". Large bold deep teal Chinese headline on the left split into two lines exactly "您的专属" and "健康服务入口". Smaller secondary text below headline exactly "点击进入，关联专属客户顾问". Strong clear contrast and precise Chinese glyphs. The headline dominates upper and middle left; illustration occupies lower right without crossing text. All text well inside a 7% safe margin; no additional text or fake buttons. Background warm ivory transitioning to pale sage at bottom, tasteful soft flowing shapes. Deliver the fully composed flat image only.
```

## 核对

检查中文内容、5:4 完整封面和 250×200 聊天缩略图：主标题和说明可读，图文无重叠。好友和朋友圈的真实微信客户端最终显示需真机复核。

## 当前版本编辑提示词

```text
Use case: text-localization / precise-object-edit. Edit this exact supplied image with one minimal localized change. Remove ONLY the small dark green subtitle "点击进入，关联专属客户顾问" located below the large headline in the left-middle area. Fill the removed text area seamlessly with the surrounding warm ivory paper texture. Keep the original image dimensions and composition. Preserve all other pixels and visual elements as closely as possible, including the brand "儒泰医联", the large two-line headline "您的专属" / "健康服务入口", typography, placement, colors, woman, face, pose, hands, folder, hospital building, trees, leaves and landscape. Do not move, resize, restyle or regenerate those elements. Keep the large headline exactly as it is. Add no new text. Output the edited flat image only.
```

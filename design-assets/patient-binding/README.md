# 客户绑定欢迎页竖版插画

v2 根据用户反馈将原有横向欢迎画面重排为 4:5 竖版，用于减少确认按钮下方的空白。页面以 widthFix 按宽度缩放。

- 当前压缩资源：`../../miniProgram/assets/images/patient-binding-welcome-v1.jpg`，750×938。
- imagegen 原图：`patient-binding-welcome-v2-original.png`。
- 上一版本：`patient-binding-welcome-previous.jpg`。
- 使用内置 imagegen 编辑生成，无外部 API。

## 最终提示词

```text
+Use case: illustration-story. Redesign the supplied existing portrait hero image for the top half of a WeChat mini-program patient binding confirmation page. Preserve its existing visual identity but recompose it into a much taller portrait canvas, aspect ratio 4:5, approximately 750×938. This hero must fill most of the screen above a one-line authorization instruction and a single button. Make the vertical artwork visually rich from top to bottom so the page has no large empty area below the button after the hero is placed. Use the canvas efficiently and do not add blank lower margin.
Keep exact Chinese brand and headline in the image, verbatim: “儒泰医联” near the top left, then “欢迎来到儒泰医联” large and clearly readable below. Keep refined heavy deep-teal Chinese typography on warm ivory handmade-paper background. Continue the existing calm sage green hills and botanical leaves. Recompose the illustrated woman healthcare adviser and small modern clinic across the lower half, preserving a friendly welcoming hand gesture and teal folder. Let the scene and flowing landscape continue down to the bottom edge. Keep headline visually above the person and building, avoid overlaps and text truncation. Deliver a professional, polished, calm Chinese health-services illustration with balanced portrait spacing and clear brand hierarchy. This is only the hero illustration. Do not render a phone, status bar, WeChat header, instruction sentence, checkbox, button, UI or border. No other text, no QR, no medical claims, no watermark.
```

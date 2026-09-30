function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]))
}

function safeUrl(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? escapeHtml(value) : ''
  } catch { return '' }
}

// Render only inside an iframe with an empty sandbox attribute. The CSP also
// blocks scripts, forms, frames and network requests from article HTML.
export function buildArticlePreview(article = {}) {
  const video = article.video
  const src = video?.status === 'ready' ? safeUrl(video.playbackUrl) : ''
  const poster = safeUrl(video?.posterUrl || article.coverImageUrl)
  const cover = safeUrl(article.coverImageUrl)
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https:; media-src https:; style-src 'unsafe-inline'"><style>body{max-width:740px;margin:24px auto;padding:0 20px;font:16px/1.9 sans-serif;color:#303133;overflow-wrap:anywhere}img,video{max-width:100%;height:auto}video{width:100%;background:#000}.meta{color:#909399;font-size:14px}h1{font-size:28px}</style></head><body><h1>${escapeHtml(article.title || '无标题')}</h1><p class="meta">${escapeHtml(article.category)}</p>${cover ? `<img src="${cover}" alt="文章封面">` : ''}<p>${escapeHtml(article.summary)}</p>${src ? `<video controls preload="metadata" src="${src}" poster="${poster}"></video>` : (video ? '<p class="meta">视频尚未就绪</p>' : '')}${article.content || '<p>暂无正文内容</p>'}</body></html>`
}

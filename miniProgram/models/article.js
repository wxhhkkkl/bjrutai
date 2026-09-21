const { formatChinaDateTime } = require('../utils/date-time')

function articleFormatError(message) {
  const error = new Error(message)
  error.kind = 'MALFORMED'
  return error
}

function normalizeArticleId(value) {
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value) || value <= 0) {
      throw articleFormatError('文章 ID 必须为正整数')
    }
    return String(value)
  }

  const text = typeof value === 'string' ? value.trim() : ''
  if (!/^\d+$/.test(text)) throw articleFormatError('文章 ID 必须为正整数')
  const normalized = text.replace(/^0+/, '')
  if (!normalized) throw articleFormatError('文章 ID 必须为正整数')
  return normalized
}

function optionalText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function imageSourceFromAttributes(attributes) {
  const match = String(attributes || '').match(/(?:^|\s)src\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/i)
  return match ? optionalText(match[1] || match[2] || match[3]) : ''
}

function isPreviewableImageUrl(value) {
  return /^https?:\/\/[^\s"'<>`]+$/i.test(value)
}

const VOID_HTML_TAGS = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'])
const BLOCKED_HTML_TAGS = new Set(['embed', 'iframe', 'object', 'script', 'style'])
const SAFE_RICH_TEXT_ATTRIBUTES = new Set(['alt', 'class', 'colspan', 'height', 'href', 'id', 'rowspan', 'src', 'style', 'target', 'title', 'width'])

function parseRichTextAttributes(value) {
  const attributes = {}
  const attributePattern = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g
  let match
  while ((match = attributePattern.exec(value))) {
    const name = match[1].toLowerCase()
    const attributeValue = match[2] || match[3] || match[4] || ''
    if (!SAFE_RICH_TEXT_ATTRIBUTES.has(name) && name !== 'data-preview-src' && name !== 'data-src') continue
    if ((name === 'src' || name === 'data-preview-src' || name === 'data-src') && !isPreviewableImageUrl(attributeValue)) continue
    attributes[name] = attributeValue
  }
  return attributes
}

function decodeRichText(value) {
  return String(value || '')
    .replace(/&nbsp;/gi, '\u00a0')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&amp;/gi, '&')
}

function parseRichTextNodes(value) {
  const roots = []
  const stack = [{ children: roots }]
  const tokens = String(value || '').match(/<!--[\s\S]*?-->|<[^>]*>|[^<]+/g) || []
  let blockedDepth = 0

  tokens.forEach((token) => {
    if (/^<!--/.test(token)) return
    if (/^<\//.test(token)) {
      const close = token.match(/^<\/\s*([a-z][\w:-]*)/i)
      if (!close) return
      if (blockedDepth) {
        blockedDepth -= 1
        return
      }
      const name = close[1].toLowerCase()
      for (let index = stack.length - 1; index > 0; index -= 1) {
        if (stack[index].name === name) {
          stack.length = index
          return
        }
      }
      return
    }

    if (/^</.test(token)) {
      const open = token.match(/^<\s*([a-z][\w:-]*)([\s\S]*?)>$/i)
      if (!open) return
      const name = open[1].toLowerCase()
      const selfClosing = /\/\s*>$/.test(token)
      if (blockedDepth || BLOCKED_HTML_TAGS.has(name)) {
        if (!selfClosing && !VOID_HTML_TAGS.has(name)) blockedDepth += 1
        return
      }

      const attrs = parseRichTextAttributes(open[2].replace(/\/\s*$/, ''))
      const node = { name }
      if (Object.keys(attrs).length) node.attrs = attrs
      stack[stack.length - 1].children.push(node)
      if (!selfClosing && !VOID_HTML_TAGS.has(name)) {
        node.children = []
        stack.push(node)
      }
      return
    }

    if (!blockedDepth && token) stack[stack.length - 1].children.push({ type: 'text', text: decodeRichText(token) })
  })

  return roots
}

function createArticleContentBlocks(value) {
  const content = String(value || '')
  const blocks = []
  const imageTagPattern = /<img\b([^>]*)>/gi
  let cursor = 0
  let match

  const addRichTextBlock = (html) => {
    if (!html) return
    const nodes = parseRichTextNodes(html)
    if (nodes.length) blocks.push({ type: 'rich-text', nodes })
  }

  while ((match = imageTagPattern.exec(content))) {
    addRichTextBlock(content.slice(cursor, match.index))
    const source = imageSourceFromAttributes(match[1])
    if (isPreviewableImageUrl(source)) {
      blocks.push({ type: 'image', src: source })
    }
    cursor = match.index + match[0].length
  }

  addRichTextBlock(content.slice(cursor))
  return blocks
}

function normalizeImageStyle(value) {
  const preservedRules = String(value || '')
    .split(';')
    .map((rule) => rule.trim())
    .filter((rule) => rule && !/^(?:width|max-width|height|max-height|display)\s*:/i.test(rule))

  return `${preservedRules.length ? `${preservedRules.join('; ')}; ` : ''}display: block; width: 100%; max-width: 100%; height: auto;`
}

function normalizeArticleContent(value) {
  const content = typeof value === 'string' ? value : ''
  const dimensionAttribute = /\s+(?:width|height)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+)/gi
  const styleAttribute = /\sstyle\s*=\s*(["'])([\s\S]*?)\1/i
  const previewDataAttribute = /\sdata-(?:preview-src|src)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+)/gi

  return content.replace(/<img\b([^>]*)>/gi, (tag, rawAttributes) => {
    let attributes = rawAttributes.replace(/\/\s*$/, '')
    const imageSource = imageSourceFromAttributes(attributes)
    const existingStyle = attributes.match(styleAttribute)
    const style = existingStyle ? existingStyle[2] : ''

    if (existingStyle) attributes = attributes.replace(existingStyle[0], '')
    attributes = attributes.replace(previewDataAttribute, '')
    attributes = attributes.replace(dimensionAttribute, '')

    const previewAttribute = isPreviewableImageUrl(imageSource)
      ? ` data-preview-src="${imageSource}" data-src="${imageSource}"`
      : ''
    return `<img${attributes}${previewAttribute} style="${normalizeImageStyle(style)}">`
  })
}

function collectArticleImageUrls(coverImageUrl, content) {
  const urls = []
  const knownUrls = new Set()
  const addUrl = (value) => {
    const url = optionalText(value)
    if (!isPreviewableImageUrl(url) || knownUrls.has(url)) return
    knownUrls.add(url)
    urls.push(url)
  }

  addUrl(coverImageUrl)
  content.replace(/<img\b([^>]*)>/gi, (tag, rawAttributes) => {
    addUrl(imageSourceFromAttributes(rawAttributes))
    return tag
  })
  return urls
}

function normalizedViewCount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : 0
}

function adaptArticleListItem(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw articleFormatError('文章列表项格式异常')
  }

  const title = optionalText(value.title)
  if (!title) throw articleFormatError('文章标题不能为空')

  const publishedAt = optionalText(value.publishedAt)
  return {
    articleId: normalizeArticleId(value.articleId),
    title,
    summary: optionalText(value.summary),
    coverImageUrl: optionalText(value.coverImageUrl),
    category: optionalText(value.category),
    author: optionalText(value.author),
    viewCount: normalizedViewCount(value.viewCount),
    publishedAt,
    publishedAtDisplay: formatChinaDateTime(publishedAt)
  }
}

function adaptArticleDetail(value) {
  const base = adaptArticleListItem(value)
  if (value.status !== 'published') {
    throw articleFormatError('文章必须为已发布状态')
  }

  const content = normalizeArticleContent(value.content)

  return Object.assign({}, base, {
    content,
    contentNodes: parseRichTextNodes(content),
    contentBlocks: createArticleContentBlocks(content),
    imageUrls: collectArticleImageUrls(base.coverImageUrl, content),
    tags: Array.isArray(value.tags)
      ? value.tags.filter((tag) => typeof tag === 'string').map((tag) => tag.trim()).filter(Boolean)
      : [],
    status: 'published',
    createdAt: optionalText(value.createdAt),
    updatedAt: optionalText(value.updatedAt)
  })
}

function createArticleShare(value) {
  const article = value && typeof value === 'object' ? value : null
  let articleId = ''

  try {
    articleId = normalizeArticleId(article && article.articleId)
  } catch (error) {
    return {
      title: '儒泰医联健康资讯',
      path: '/pages/home/index',
      imageUrl: ''
    }
  }

  return {
    title: optionalText(article.title) || '儒泰医联健康资讯',
    path: `/pages/article-detail/index?articleId=${encodeURIComponent(articleId)}`,
    imageUrl: optionalText(article.coverImageUrl)
  }
}

function adaptArticlePage(value) {
  if (!value || typeof value !== 'object' || !Array.isArray(value.items)) {
    throw articleFormatError('文章分页 items 格式异常')
  }
  if (typeof value.hasMore !== 'boolean') {
    throw articleFormatError('文章分页 hasMore 格式异常')
  }

  const nextCursor = value.hasMore ? optionalText(value.nextCursor) : ''
  if (value.hasMore && !nextCursor) {
    throw articleFormatError('文章分页游标缺失')
  }

  return {
    items: value.items.map(adaptArticleListItem),
    nextCursor,
    hasMore: value.hasMore
  }
}

function adaptArticleCategories(value) {
  if (!value || typeof value !== 'object' || !Array.isArray(value.items)) {
    throw articleFormatError('文章分类列表格式异常')
  }

  const knownIds = new Set()
  return value.items.reduce((categories, item) => {
    const name = optionalText(item && item.name)
    let id = ''
    try {
      id = normalizeArticleId(item && item.id)
    } catch (error) {
      return categories
    }
    if (!name || name.length > 50 || knownIds.has(id)) return categories
    knownIds.add(id)
    categories.push({ id, name })
    return categories
  }, [])
}

function mergeArticlePage(existingItems, page, currentCursor = '') {
  const items = Array.isArray(existingItems) ? existingItems.slice() : []
  const knownIds = new Set(items.map((item) => item.articleId))
  let added = 0

  page.items.forEach((item) => {
    if (knownIds.has(item.articleId)) return
    knownIds.add(item.articleId)
    items.push(item)
    added += 1
  })

  const hasProgress = !page.hasMore || (
    added > 0 && page.nextCursor && page.nextCursor !== currentCursor
  )
  if (!hasProgress) {
    return {
      items,
      nextCursor: '',
      hasMore: false,
      paginationError: '文章分页数据未继续推进，请下拉刷新后重试'
    }
  }

  return {
    items,
    nextCursor: page.hasMore ? page.nextCursor : '',
    hasMore: page.hasMore,
    paginationError: ''
  }
}

module.exports = {
  normalizeArticleId,
  adaptArticleListItem,
  adaptArticleDetail,
  createArticleShare,
  adaptArticlePage,
  adaptArticleCategories,
  mergeArticlePage
}

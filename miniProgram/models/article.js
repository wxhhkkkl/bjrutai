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

  return Object.assign({}, base, {
    content: typeof value.content === 'string' ? value.content : '',
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

const { request } = require('./request-service')
const { normalizeArticleId } = require('../models/article')

function normalizeLimit(value) {
  if (value === undefined) return 20
  if (!Number.isInteger(value) || value < 1 || value > 100) {
    throw new Error('文章分页数量必须为 1 到 100 的整数')
  }
  return value
}

function normalizeCategory(value) {
  if (value === undefined || value === null) return ''
  const category = String(value).trim()
  if (category.length > 50) throw new Error('文章分类不能超过 50 个字符')
  return category
}

function listArticles(options = {}) {
  const data = { limit: normalizeLimit(options.limit) }
  const category = normalizeCategory(options.category)
  if (category) data.category = category
  if (options.cursor !== undefined && options.cursor !== null && options.cursor !== '') {
    data.cursor = String(options.cursor)
  }
  return request('/api/v1/articles', { auth: false, data })
}

function listArticleCategories() {
  return request('/api/v1/articles/categories', { auth: false })
}

function getArticle(articleId) {
  const normalizedId = normalizeArticleId(articleId)
  return request(`/api/v1/articles/${encodeURIComponent(normalizedId)}`, { auth: false })
}

module.exports = {
  listArticles,
  listArticleCategories,
  getArticle
}

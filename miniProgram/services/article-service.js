const { request } = require('./request-service')
const { normalizeArticleId } = require('../models/article')

function normalizeLimit(value) {
  if (value === undefined) return 20
  if (!Number.isInteger(value) || value < 1 || value > 100) {
    throw new Error('文章分页数量必须为 1 到 100 的整数')
  }
  return value
}

function listArticles(options = {}) {
  const data = { limit: normalizeLimit(options.limit) }
  if (options.cursor !== undefined && options.cursor !== null && options.cursor !== '') {
    data.cursor = String(options.cursor)
  }
  return request('/api/v1/articles', { auth: false, data })
}

function getArticle(articleId) {
  const normalizedId = normalizeArticleId(articleId)
  return request(`/api/v1/articles/${encodeURIComponent(normalizedId)}`, { auth: false })
}

module.exports = {
  listArticles,
  getArticle
}

const { request } = require('./request-service')
const { normalizeArticleId } = require('../models/article')
const { normalizeCommentId, createCommentIdempotencyKey } = require('../models/comment')

function normalizeLimit(value) {
  if (value === undefined) return 20
  if (!Number.isInteger(value) || value < 1 || value > 50) {
    throw new Error('评论分页数量必须为 1 到 50 的整数')
  }
  return value
}

function listComments(articleId, options = {}) {
  const article = normalizeArticleId(articleId)
  const data = { limit: normalizeLimit(options.limit) }
  if (options.cursor !== undefined && options.cursor !== null && options.cursor !== '') {
    data.cursor = String(options.cursor)
  }
  return request(`/api/v1/articles/${encodeURIComponent(article)}/comments`, { data })
}

function createComment(articleId, content, idempotencyKey = createCommentIdempotencyKey()) {
  const article = normalizeArticleId(articleId)
  const value = typeof content === 'string' ? content.trim() : ''
  if (!value || value.length > 500) throw new Error('评论内容必须为 1 到 500 个字符')
  return request(`/api/v1/articles/${encodeURIComponent(article)}/comments`, {
    method: 'POST',
    data: { content: value },
    idempotencyKey
  })
}

function likeComment(articleId, commentId) {
  const article = normalizeArticleId(articleId)
  const comment = normalizeCommentId(commentId)
  return request(
    `/api/v1/articles/${encodeURIComponent(article)}/comments/${encodeURIComponent(comment)}/like`,
    { method: 'POST' }
  )
}

function unlikeComment(articleId, commentId) {
  const article = normalizeArticleId(articleId)
  const comment = normalizeCommentId(commentId)
  return request(
    `/api/v1/articles/${encodeURIComponent(article)}/comments/${encodeURIComponent(comment)}/like`,
    { method: 'DELETE' }
  )
}

module.exports = {
  listComments,
  createComment,
  likeComment,
  unlikeComment
}

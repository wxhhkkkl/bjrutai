const { formatChinaDateTime } = require('../utils/date-time')

function commentFormatError(message) {
  const error = new Error(message)
  error.kind = 'MALFORMED'
  return error
}

function normalizeCommentId(value) {
  const text = typeof value === 'number' ? String(value) : String(value || '').trim()
  if (!/^\d+$/.test(text) || Number(text) <= 0) {
    throw commentFormatError('评论 ID 必须为正整数')
  }
  return text.replace(/^0+/, '') || '0'
}

function optionalText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function adaptComment(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw commentFormatError('评论格式异常')
  }
  const content = optionalText(value.content)
  if (!content) throw commentFormatError('评论内容不能为空')
  const createdAt = optionalText(value.createdAt)
  return {
    commentId: normalizeCommentId(value.commentId),
    displayName: optionalText(value.displayName) || '儒泰用户',
    avatarUrl: optionalText(value.avatarUrl),
    content,
    isPinned: value.isPinned === true,
    likeCount: Number.isSafeInteger(value.likeCount) && value.likeCount >= 0 ? value.likeCount : 0,
    liked: value.liked === true,
    createdAt,
    createdAtDisplay: formatChinaDateTime(createdAt)
  }
}

function adaptCommentPage(value) {
  if (!value || typeof value !== 'object' || !Array.isArray(value.items)) {
    throw commentFormatError('评论列表格式异常')
  }
  if (typeof value.hasMore !== 'boolean') throw commentFormatError('评论分页状态异常')
  const nextCursor = optionalText(value.nextCursor)
  if (value.hasMore && !nextCursor) throw commentFormatError('评论分页游标缺失')
  return {
    items: value.items.map(adaptComment),
    nextCursor: value.hasMore ? nextCursor : '',
    hasMore: value.hasMore,
    total: Number.isSafeInteger(value.total) && value.total >= 0 ? value.total : 0
  }
}

function adaptLikeResult(value) {
  if (!value || typeof value !== 'object') throw commentFormatError('点赞响应格式异常')
  return {
    commentId: normalizeCommentId(value.commentId),
    liked: value.liked === true,
    likeCount: Number.isSafeInteger(value.likeCount) && value.likeCount >= 0 ? value.likeCount : 0
  }
}

function createCommentIdempotencyKey() {
  const random = Math.random().toString(36).slice(2, 10)
  return `comment-${Date.now()}-${random}`
}

module.exports = {
  normalizeCommentId,
  adaptComment,
  adaptCommentPage,
  adaptLikeResult,
  createCommentIdempotencyKey
}

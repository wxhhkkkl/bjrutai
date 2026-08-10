const test = require('node:test')
const assert = require('node:assert/strict')

const {
  normalizeArticleId,
  adaptArticleListItem,
  adaptArticleDetail,
  adaptArticlePage,
  mergeArticlePage
} = require('../../models/article')

const listItem = {
  articleId: '12',
  title: ' 夏季健康管理提示 ',
  summary: null,
  coverImageUrl: null,
  category: null,
  author: ' 内容团队 ',
  viewCount: 36,
  publishedAt: '2026-08-10T07:30:00Z'
}

test('validates and normalizes positive article ids without losing string ids', () => {
  assert.equal(normalizeArticleId('0012'), '12')
  assert.equal(normalizeArticleId(12), '12')
  assert.equal(normalizeArticleId('9223372036854775807'), '9223372036854775807')
  for (const value of ['', '0', '-1', '1.2', 'abc', null, Number.MAX_SAFE_INTEGER + 2]) {
    assert.throws(() => normalizeArticleId(value), /文章 ID/)
  }
})

test('adapts optional list fields, server view count and China display time', () => {
  assert.deepEqual(adaptArticleListItem(listItem), {
    articleId: '12',
    title: '夏季健康管理提示',
    summary: '',
    coverImageUrl: '',
    category: '',
    author: '内容团队',
    viewCount: 36,
    publishedAt: '2026-08-10T07:30:00Z',
    publishedAtDisplay: '2026年8月10日 15:30'
  })
  assert.equal(adaptArticleListItem({ ...listItem, viewCount: -1 }).viewCount, 0)
  assert.throws(() => adaptArticleListItem({ ...listItem, title: '  ' }), /文章标题/)
})

test('detail accepts published content only and filters malformed tags', () => {
  const detail = adaptArticleDetail({
    ...listItem,
    content: '<p>正文</p>',
    tags: [' 健康 ', '', 123],
    status: 'published',
    createdAt: '2026-08-09T03:00:00Z',
    updatedAt: null
  })
  assert.equal(detail.content, '<p>正文</p>')
  assert.deepEqual(detail.tags, ['健康'])
  assert.equal(detail.status, 'published')
  assert.equal(detail.createdAt, '2026-08-09T03:00:00Z')
  assert.equal(detail.updatedAt, '')
  assert.throws(() => adaptArticleDetail({ ...listItem, status: 'draft' }), /已发布/)
})

test('article page requires valid pagination data and treats cursor as opaque', () => {
  const page = adaptArticlePage({ items: [listItem], nextCursor: 'opaque+/=', hasMore: true })
  assert.equal(page.nextCursor, 'opaque+/=')
  assert.equal(page.hasMore, true)
  assert.throws(() => adaptArticlePage({ items: null, hasMore: false }), /items/)
  assert.throws(() => adaptArticlePage({ items: [], nextCursor: '', hasMore: true }), /游标/)
  assert.throws(() => adaptArticlePage({ items: [], hasMore: 'false' }), /hasMore/)
})

test('merges cursor pages by articleId and stops pagination without progress', () => {
  const existing = [adaptArticleListItem(listItem)]
  const next = adaptArticlePage({
    items: [listItem, { ...listItem, articleId: '13', title: '新文章' }],
    nextCursor: 'next',
    hasMore: true
  })
  assert.deepEqual(mergeArticlePage(existing, next, 'current'), {
    items: [existing[0], adaptArticleListItem({ ...listItem, articleId: '13', title: '新文章' })],
    nextCursor: 'next',
    hasMore: true,
    paginationError: ''
  })

  const duplicateOnly = adaptArticlePage({ items: [listItem], nextCursor: 'next', hasMore: true })
  assert.equal(mergeArticlePage(existing, duplicateOnly, 'current').hasMore, false)
  assert.match(mergeArticlePage(existing, duplicateOnly, 'current').paginationError, /分页/)

  const sameCursor = adaptArticlePage({
    items: [{ ...listItem, articleId: '14' }], nextCursor: 'current', hasMore: true
  })
  assert.equal(mergeArticlePage(existing, sameCursor, 'current').hasMore, false)
})

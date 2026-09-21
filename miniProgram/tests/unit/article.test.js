const test = require('node:test')
const assert = require('node:assert/strict')

const {
  normalizeArticleId,
  adaptArticleListItem,
  adaptArticleDetail,
  adaptArticlePage,
  adaptArticleCategories,
  createArticleShare,
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

function findRichTextNode(nodes, name) {
  for (const node of nodes || []) {
    if (node && node.name === name) return node
    const child = findRichTextNode(node && node.children, name)
    if (child) return child
  }
  return null
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

test('detail makes backend rich-text images fit the mini-program content width', () => {
  const detail = adaptArticleDetail({
    ...listItem,
    coverImageUrl: 'https://cdn.example.test/article-cover.png',
    content: '<p><img src="https://cdn.example.test/article.png" alt="文章配图" width="1600" height="2400" style="width: 800px; height: 1200px; border-radius: 8px"></p><p><img src="https://cdn.example.test/article.png"><img src="https://cdn.example.test/second.png"></p>',
    status: 'published'
  })

  assert.match(detail.content, /src="https:\/\/cdn\.example\.test\/article\.png"/)
  assert.match(detail.content, /alt="文章配图"/)
  assert.doesNotMatch(detail.content, /\swidth="1600"/)
  assert.doesNotMatch(detail.content, /\sheight="2400"/)
  assert.match(detail.content, /border-radius:\s*8px/)
  assert.match(detail.content, /display:\s*block/)
  assert.match(detail.content, /width:\s*100%/)
  assert.match(detail.content, /max-width:\s*100%/)
  assert.match(detail.content, /height:\s*auto/)
  assert.match(detail.content, /data-preview-src="https:\/\/cdn\.example\.test\/article\.png"/)
  assert.ok(Array.isArray(detail.contentNodes))
  assert.equal(
    findRichTextNode(detail.contentNodes, 'img').attrs['data-preview-src'],
    'https://cdn.example.test/article.png'
  )
  assert.equal(
    findRichTextNode(detail.contentNodes, 'img').attrs['data-src'],
    'https://cdn.example.test/article.png'
  )
  assert.deepEqual(
    detail.contentBlocks.filter((block) => block.type === 'image').map((block) => block.src),
    [
      'https://cdn.example.test/article.png',
      'https://cdn.example.test/article.png',
      'https://cdn.example.test/second.png'
    ]
  )
  assert.deepEqual(detail.imageUrls, [
    'https://cdn.example.test/article-cover.png',
    'https://cdn.example.test/article.png',
    'https://cdn.example.test/second.png'
  ])
})

test('creates a public article share payload without exposing unavailable article ids', () => {
  assert.deepEqual(createArticleShare({
    articleId: '0012',
    title: ' 夏季健康管理提示 ',
    coverImageUrl: 'https://cdn.example.test/article-cover.png'
  }), {
    title: '夏季健康管理提示',
    path: '/pages/article-detail/index?articleId=12',
    imageUrl: 'https://cdn.example.test/article-cover.png'
  })
  assert.deepEqual(createArticleShare(null), {
    title: '儒泰医联健康资讯',
    path: '/pages/home/index',
    imageUrl: ''
  })
})

test('article page requires valid pagination data and treats cursor as opaque', () => {
  const page = adaptArticlePage({ items: [listItem], nextCursor: 'opaque+/=', hasMore: true })
  assert.equal(page.nextCursor, 'opaque+/=')
  assert.equal(page.hasMore, true)
  assert.throws(() => adaptArticlePage({ items: null, hasMore: false }), /items/)
  assert.throws(() => adaptArticlePage({ items: [], nextCursor: '', hasMore: true }), /游标/)
  assert.throws(() => adaptArticlePage({ items: [], hasMore: 'false' }), /hasMore/)
})

test('adapts only valid unique article categories for the public filter', () => {
  assert.deepEqual(adaptArticleCategories({
    items: [
      { id: '1', name: ' 健康科普 ' },
      { id: '2', name: '服务动态' },
      { id: '2', name: '重复项' },
      { id: 'bad', name: '无效项' }
    ]
  }), [
    { id: '1', name: '健康科普' },
    { id: '2', name: '服务动态' }
  ])
  assert.throws(() => adaptArticleCategories({}), /分类列表/)
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

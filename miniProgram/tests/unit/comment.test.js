const test = require('node:test')
const assert = require('node:assert/strict')

const {
  adaptComment,
  adaptCommentPage,
  adaptLikeResult,
  createCommentIdempotencyKey
} = require('../../models/comment')

test('normalizes a public comment item without exposing user identifiers', () => {
  assert.deepEqual(adaptComment({
    commentId: '009',
    displayName: ' 评论用户 ',
    avatarUrl: null,
    content: ' 很实用 😊 ',
    isPinned: true,
    likeCount: 3,
    liked: false,
    createdAt: '2026-09-21T08:00:00Z',
    userId: 'must-not-be-returned'
  }), {
    commentId: '9',
    displayName: '评论用户',
    avatarUrl: '',
    content: '很实用 😊',
    isPinned: true,
    likeCount: 3,
    liked: false,
    createdAt: '2026-09-21T08:00:00Z',
    createdAtDisplay: '2026年9月21日 16:00'
  })
})

test('validates cursor pages and clamps unsafe counts', () => {
  const page = adaptCommentPage({
    items: [{
      commentId: '1', displayName: '用户', content: '内容', isPinned: false,
      likeCount: -3, liked: true, createdAt: '2026-09-21T08:00:00Z'
    }],
    nextCursor: 'opaque+/=',
    hasMore: true,
    total: 1
  })
  assert.equal(page.items[0].likeCount, 0)
  assert.equal(page.nextCursor, 'opaque+/=')
  assert.throws(() => adaptCommentPage({ items: [], hasMore: true, total: 0 }), /游标/)
})

test('creates a unique idempotency key and adapts like responses', () => {
  const first = createCommentIdempotencyKey()
  const second = createCommentIdempotencyKey()
  assert.match(first, /^comment-/)
  assert.notEqual(first, second)
  assert.deepEqual(adaptLikeResult({ commentId: '007', liked: true, likeCount: 2 }), {
    commentId: '7', liked: true, likeCount: 2
  })
})

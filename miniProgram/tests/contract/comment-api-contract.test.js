const test = require('node:test')
const assert = require('node:assert/strict')

function loadServiceWithRequestSpy(spy) {
  const requestPath = require.resolve('../../services/request-service')
  const servicePath = require.resolve('../../services/comment-service')
  const originalRequestModule = require.cache[requestPath]
  const originalServiceModule = require.cache[servicePath]
  require.cache[requestPath] = { id: requestPath, filename: requestPath, loaded: true, exports: { request: spy } }
  delete require.cache[servicePath]
  const service = require('../../services/comment-service')
  return {
    service,
    restore() {
      if (originalRequestModule) require.cache[requestPath] = originalRequestModule
      else delete require.cache[requestPath]
      if (originalServiceModule) require.cache[servicePath] = originalServiceModule
      else delete require.cache[servicePath]
    }
  }
}

test('loads a visible comment page with the existing Bearer token and cursor', async () => {
  const calls = []
  const loaded = loadServiceWithRequestSpy(async (path, options) => {
    calls.push({ path, options })
    return { items: [], nextCursor: null, hasMore: false, total: 0 }
  })
  try {
    await loaded.service.listComments('009', { cursor: 'opaque+/=', limit: 10 })
    assert.deepEqual(calls[0], {
      path: '/api/v1/articles/9/comments',
      options: { data: { cursor: 'opaque+/=', limit: 10 } }
    })
  } finally {
    loaded.restore()
  }
})

test('submits a comment with an Idempotency-Key and preserves the response envelope', async () => {
  const calls = []
  const loaded = loadServiceWithRequestSpy(async (path, options) => {
    calls.push({ path, options })
    return { commentId: '1', status: 'visible', moderationStatus: 'passed' }
  })
  try {
    const result = await loaded.service.createComment('3', '很实用 😊', 'comment-contract-1')
    assert.equal(result.commentId, '1')
    assert.deepEqual(calls[0], {
      path: '/api/v1/articles/3/comments',
      options: { method: 'POST', data: { content: '很实用 😊' }, idempotencyKey: 'comment-contract-1' }
    })
  } finally {
    loaded.restore()
  }
})

test('maps login expiry and validation errors without leaking comment content', async () => {
  const loaded = loadServiceWithRequestSpy(async () => {
    throw Object.assign(new Error('登录已过期'), { kind: 'AUTH', code: 40100 })
  })
  try {
    await assert.rejects(loaded.service.listComments('1'), (error) => {
      assert.equal(error.kind, 'AUTH')
      assert.doesNotMatch(JSON.stringify(error), /评论正文/)
      return true
    })
  } finally {
    loaded.restore()
  }
})

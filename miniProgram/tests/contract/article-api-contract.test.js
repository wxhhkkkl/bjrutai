const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadService(result = {}) {
  const servicePath = path.resolve(__dirname, '../../services/article-service.js')
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const originalRequest = require.cache[requestPath]
  const calls = []
  delete require.cache[servicePath]
  require.cache[requestPath] = {
    id: requestPath,
    filename: requestPath,
    loaded: true,
    exports: {
      request(apiPath, options = {}) {
        calls.push({ path: apiPath, options })
        return Promise.resolve(result)
      }
    }
  }
  return {
    service: require(servicePath),
    calls,
    restore() {
      delete require.cache[servicePath]
      if (originalRequest) require.cache[requestPath] = originalRequest
      else delete require.cache[requestPath]
    }
  }
}

test('article service uses public list contract and preserves an opaque cursor', async () => {
  const fixture = loadService()
  try {
    await fixture.service.listArticles({ limit: 20, cursor: 'opaque+/=', category: 'ignored' })
    await fixture.service.listArticles({ limit: 3 })
    assert.deepEqual(fixture.calls, [{
      path: '/api/v1/articles',
      options: { auth: false, data: { limit: 20, cursor: 'opaque+/=' } }
    }, {
      path: '/api/v1/articles',
      options: { auth: false, data: { limit: 3 } }
    }])
  } finally {
    fixture.restore()
  }
})

test('article service validates ids before a public detail request', async () => {
  const fixture = loadService()
  try {
    await fixture.service.getArticle('0012')
    assert.deepEqual(fixture.calls[0], {
      path: '/api/v1/articles/12',
      options: { auth: false }
    })
    assert.throws(() => fixture.service.getArticle('../admin'), /文章 ID/)
    assert.equal(fixture.calls.length, 1)
  } finally {
    fixture.restore()
  }
})

test('article service leaves unified 404 and malformed handling to request-service', async () => {
  const fixture = loadService()
  try {
    assert.equal(typeof fixture.service.listArticles, 'function')
    assert.equal(typeof fixture.service.getArticle, 'function')
    assert.equal(typeof fixture.service.getAdminArticles, 'undefined')
    assert.equal(typeof fixture.service.getMockArticles, 'undefined')
  } finally {
    fixture.restore()
  }
})

const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function loadPage(relativePath, service) {
  const pagePath = path.resolve(__dirname, '../../', relativePath)
  const servicePath = path.resolve(__dirname, '../../services/article-service.js')
  const originalService = require.cache[servicePath]
  const originalPage = global.Page
  const originalWx = global.wx
  let definition
  const navigations = []

  delete require.cache[pagePath]
  require.cache[servicePath] = {
    id: servicePath,
    filename: servicePath,
    loaded: true,
    exports: service
  }
  global.Page = (value) => { definition = value }
  global.wx = {
    navigateTo(options) { navigations.push(options.url); if (options.success) options.success() },
    navigateBack() {},
    switchTab() {},
    stopPullDownRefresh() {}
  }
  require(pagePath)

  const page = Object.assign({}, definition, {
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(values) { this.data = Object.assign({}, this.data, values) }
  })
  return {
    page,
    navigations,
    restore() {
      delete require.cache[pagePath]
      if (originalService) require.cache[servicePath] = originalService
      else delete require.cache[servicePath]
      global.Page = originalPage
      global.wx = originalWx
    }
  }
}

const item = {
  articleId: '12', title: '文章一', summary: '摘要', coverImageUrl: '', category: '科普',
  author: '内容团队', viewCount: 6, publishedAt: '2026-08-10T07:30:00Z'
}

const detail = {
  ...item, content: '<p>正文</p>', tags: [], status: 'published',
  createdAt: '2026-08-09T03:00:00Z', updatedAt: '2026-08-10T07:30:00Z', viewCount: 7
}

test('detail validates id locally, loads once on entry and uses server view count', async () => {
  const calls = []
  const fixture = loadPage('pages/article-detail/index.js', {
    getArticle(id) { calls.push(id); return Promise.resolve(detail) }
  })
  try {
    fixture.page.onLoad({ articleId: '0012' })
    await flush()
    assert.deepEqual(calls, ['12'])
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.article.viewCount, 7)
    if (fixture.page.onShow) fixture.page.onShow()
    await flush()
    assert.equal(calls.length, 1)

    fixture.page.retry()
    await flush()
    assert.equal(calls.length, 2)
  } finally {
    fixture.restore()
  }
})

test('detail invalid id sends no request and late or 404 responses never expose old body', async () => {
  const pending = deferred()
  let calls = 0
  const fixture = loadPage('pages/article-detail/index.js', {
    getArticle() { calls += 1; return pending.promise }
  })
  try {
    fixture.page.onLoad({ articleId: '../admin' })
    assert.equal(calls, 0)
    assert.equal(fixture.page.data.state, 'not-found')

    fixture.page.onLoad({ articleId: '12' })
    fixture.page.onUnload()
    pending.resolve(detail)
    await flush()
    assert.notEqual(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.article, null)
  } finally {
    fixture.restore()
  }

  const notFoundFixture = loadPage('pages/article-detail/index.js', {
    getArticle() { return Promise.reject({ kind: 'NOT_FOUND', message: 'not found' }) }
  })
  try {
    notFoundFixture.page.data.article = detail
    notFoundFixture.page.onLoad({ articleId: '12' })
    await flush()
    assert.equal(notFoundFixture.page.data.state, 'not-found')
    assert.equal(notFoundFixture.page.data.article, null)
    assert.match(notFoundFixture.page.data.stateMessage, /下架|不存在/)
  } finally {
    notFoundFixture.restore()
  }
})

test('list replaces first page, appends cursor page, deduplicates and prevents concurrent loads', async () => {
  const more = deferred()
  const calls = []
  const fixture = loadPage('pages/articles/index.js', {
    listArticles(options) {
      calls.push(options)
      if (calls.length === 1) return Promise.resolve({ items: [item], nextCursor: 'c1', hasMore: true })
      return more.promise
    }
  })
  try {
    fixture.page.onLoad()
    await flush()
    assert.equal(fixture.page.data.state, 'success')
    assert.deepEqual(calls, [{ limit: 20 }])

    fixture.page.onReachBottom()
    fixture.page.onReachBottom()
    assert.equal(calls.length, 2)
    assert.deepEqual(calls[1], { limit: 20, cursor: 'c1' })
    more.resolve({
      items: [item, { ...item, articleId: '13', title: '文章二' }],
      nextCursor: null,
      hasMore: false
    })
    await flush()
    assert.deepEqual(fixture.page.data.items.map((value) => value.articleId), ['12', '13'])
    assert.equal(fixture.page.data.hasMore, false)
  } finally {
    fixture.restore()
  }
})

test('list keeps loaded content on pagination failure and guards detail navigation', async () => {
  let calls = 0
  const fixture = loadPage('pages/articles/index.js', {
    listArticles() {
      calls += 1
      if (calls === 1) return Promise.resolve({ items: [item], nextCursor: 'c1', hasMore: true })
      return Promise.reject({ kind: 'NETWORK', message: '网络异常' })
    }
  })
  try {
    fixture.page.onLoad()
    await flush()
    fixture.page.onReachBottom()
    await flush()
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.items.length, 1)
    assert.match(fixture.page.data.loadMoreError, /网络异常/)

    const event = { currentTarget: { dataset: { id: '12' } } }
    fixture.page.openArticle(event)
    fixture.page.openArticle(event)
    assert.deepEqual(fixture.navigations, ['/pages/article-detail/index?articleId=12'])
  } finally {
    fixture.restore()
  }
})

test('pull-down refresh discards the late response from an older load', async () => {
  const first = deferred()
  let calls = 0
  const fixture = loadPage('pages/articles/index.js', {
    listArticles() {
      calls += 1
      if (calls === 1) return first.promise
      return Promise.resolve({
        items: [{ ...item, articleId: '20', title: '刷新后的文章' }],
        nextCursor: null,
        hasMore: false
      })
    }
  })
  try {
    fixture.page.onLoad()
    fixture.page.onPullDownRefresh()
    await flush()
    first.resolve({ items: [item], nextCursor: null, hasMore: false })
    await flush()
    assert.deepEqual(fixture.page.data.items.map((value) => value.articleId), ['20'])
  } finally {
    fixture.restore()
  }
})

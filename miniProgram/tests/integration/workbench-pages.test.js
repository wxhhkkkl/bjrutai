const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '../..')

test('home and profile production pages use real workbench service and no Demo fixtures', () => {
  for (const relative of ['pages/home/index.js', 'pages/profile/index.js']) {
    const source = fs.readFileSync(path.join(root, relative), 'utf8')
    assert.match(source, /workbench-service/)
    assert.doesNotMatch(source, /mock\/demo-control|mock\/foundation-fixtures/)
    assert.match(source, /state:\s*['"]loading['"]/)
    assert.match(source, /recoverable-error/)
  }
})

test('home and profile guard page state against stale asynchronous responses', () => {
  for (const relative of ['pages/home/index.js', 'pages/profile/index.js']) {
    const source = fs.readFileSync(path.join(root, relative), 'utf8')
    assert.match(source, /requestVersion/)
    assert.match(source, /version\s*!==\s*this\.requestVersion/)
  }
})

test('workbench pages expose empty and forbidden state handling', () => {
  const home = fs.readFileSync(path.join(root, 'pages/home/index.js'), 'utf8')
  const profile = fs.readFileSync(path.join(root, 'pages/profile/index.js'), 'utf8')
  assert.match(home, /empty/)
  assert.match(home, /forbidden/)
  assert.match(profile, /empty/)
  assert.match(profile, /forbidden/)
})

test('profile fills the regular-user 2 by 2 service grid with article reading', () => {
  const source = fs.readFileSync(path.join(root, 'pages/profile/index.js'), 'utf8')
  assert.match(source, /id:\s*['"]article-list['"]/)
  assert.match(source, /title:\s*['"]文章资讯['"]/)
  assert.match(source, /description:\s*['"]阅读最新内容['"]/)
  assert.match(source, /profile-article-icon\.png/)
  assert.ok(source.indexOf("id: 'article-list'") > source.indexOf("id: 'contribution-detail'"))
  assert.match(source, /adminOnly/)
})

test('home article state is isolated from the core workbench state', () => {
  const source = fs.readFileSync(path.join(root, 'pages/home/index.js'), 'utf8')
  assert.match(source, /articleState:\s*['"]loading['"]/)
  assert.match(source, /articleItems:\s*\[\]/)
  assert.match(source, /articleRequestVersion/)
  assert.match(source, /listArticles\(\{\s*limit:\s*3\s*\}\)/)
  assert.match(source, /version\s*!==\s*this\.articleRequestVersion/)
})

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function loadHome(articleService) {
  const pagePath = path.join(root, 'pages/home/index.js')
  const moduleStubs = {
    [path.join(root, 'services/article-service.js')]: articleService,
    [path.join(root, 'services/session-service.js')]: {
      getCurrentSession() { return { userId: 'u1', role: 'promoter', activationStatus: 'active' } },
      getEntry() { return { type: 'stay' } }
    },
    [path.join(root, 'services/workbench-service.js')]: {
      getWorkbench() { return Promise.resolve({ role: 'promoter', metrics: { myCustomers: 1, myBindings: 2, myMonthlyConsumption: 0, pendingFollowups: 0 } }) },
      getNotices() { return Promise.resolve({ notices: [] }) },
      getRecentBindings() { return Promise.resolve({ items: [] }) }
    },
    [path.join(root, 'services/navigation-service.js')]: {
      openAction() { return { ok: true, url: '/pages/articles/index' } },
      updateTabBar() {}
    }
  }
  const originals = new Map()
  for (const [modulePath, exports] of Object.entries(moduleStubs)) {
    originals.set(modulePath, require.cache[modulePath])
    require.cache[modulePath] = { id: modulePath, filename: modulePath, loaded: true, exports }
  }
  const originalPage = global.Page
  const originalWx = global.wx
  let definition
  global.Page = (value) => { definition = value }
  global.wx = { reLaunch() {}, navigateTo() {}, showModal() {}, showToast() {} }
  delete require.cache[pagePath]
  require(pagePath)
  const page = Object.assign({}, definition, {
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(values) { this.data = Object.assign({}, this.data, values) }
  })
  return {
    page,
    restore() {
      delete require.cache[pagePath]
      for (const [modulePath, original] of originals.entries()) {
        if (original) require.cache[modulePath] = original
        else delete require.cache[modulePath]
      }
      global.Page = originalPage
      global.wx = originalWx
    }
  }
}

test('article request failure does not change a successful home workbench', async () => {
  const fixture = loadHome({
    listArticles() { return Promise.reject({ kind: 'NETWORK', message: '文章网络异常' }) }
  })
  try {
    fixture.page.onShow()
    await flush()
    await flush()
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.articleState, 'recoverable-error')
    assert.equal(fixture.page.data.summary.firstMetricValue, '1')
  } finally {
    fixture.restore()
  }
})

test('home discards an article response arriving after the page hides', async () => {
  let resolveArticle
  const fixture = loadHome({
    listArticles() { return new Promise((resolve) => { resolveArticle = resolve }) }
  })
  try {
    fixture.page.loadArticles()
    fixture.page.onHide()
    resolveArticle({ items: [{ articleId: '1', title: '迟到文章', viewCount: 0 }], nextCursor: null, hasMore: false })
    await flush()
    assert.notEqual(fixture.page.data.articleState, 'success')
    assert.deepEqual(fixture.page.data.articleItems, [])
  } finally {
    fixture.restore()
  }
})

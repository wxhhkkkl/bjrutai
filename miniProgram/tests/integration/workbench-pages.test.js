const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '../..')

test('home is a public health-content page while profile keeps its workbench integration', () => {
  const home = fs.readFileSync(path.join(root, 'pages/home/index.js'), 'utf8')
  const homeMarkup = fs.readFileSync(path.join(root, 'pages/home/index.wxml'), 'utf8')
  const profile = fs.readFileSync(path.join(root, 'pages/profile/index.js'), 'utf8')

  assert.match(home, /article-service/)
  assert.match(home, /banner-service/)
  assert.doesNotMatch(home, /workbench-service/)
  assert.doesNotMatch(homeMarkup, /快捷服务|业务概览/)
  assert.match(homeMarkup, /关于儒泰/)
  assert.doesNotMatch(homeMarkup, /about-card__cover-shade|about-card__cover-brand|about-card__cover-label/)
  assert.match(homeMarkup, /心脑维养/)
  assert.match(homeMarkup, /wellness-feature__cover/)
  assert.match(homeMarkup, /\{\{wellnessLead\.title\}\}/)
  assert.match(homeMarkup, /wx:for="\{\{wellnessSupportingItems\}\}"/)
  assert.match(homeMarkup, /data-category="心脑维养"/)
  assert.match(homeMarkup, /class="section-more tap-target"/)
  assert.match(homeMarkup, /data-category="关于儒泰"/)
  assert.doesNotMatch(homeMarkup, /class="heading-link tap-target"/)
  assert.match(home, /openArticleCategory/)
  assert.match(homeMarkup, /文章资讯/)
  assert.match(homeMarkup, /wellness-grid/)
  assert.doesNotMatch(homeMarkup, /科学认知|生活维养|持续陪伴/)
  assert.doesNotMatch(homeMarkup, /wellness-link|查看心脑健康资讯/)
  assert.ok(homeMarkup.indexOf('心脑维养') < homeMarkup.indexOf('健康资讯'))
  assert.ok(homeMarkup.indexOf('健康资讯') < homeMarkup.lastIndexOf('关于儒泰'))
  assert.match(profile, /workbench-service/)
  assert.doesNotMatch(home, /mock\/demo-control|mock\/foundation-fixtures/)
})

test('content requests and profile workbench requests discard stale responses', () => {
  const home = fs.readFileSync(path.join(root, 'pages/home/index.js'), 'utf8')
  const profile = fs.readFileSync(path.join(root, 'pages/profile/index.js'), 'utf8')
  assert.match(home, /articleRequestVersion/)
  assert.match(home, /bannerRequestVersion/)
  assert.match(home, /version\s*!==\s*this\.articleRequestVersion/)
  assert.match(home, /version\s*!==\s*this\.bannerRequestVersion/)
  assert.match(profile, /requestVersion/)
  assert.match(profile, /version\s*!==\s*this\.requestVersion/)
})

test('profile retains empty and forbidden state handling', () => {
  const profile = fs.readFileSync(path.join(root, 'pages/profile/index.js'), 'utf8')
  assert.match(profile, /empty/)
  assert.match(profile, /forbidden/)
})

test('profile exposes role-gated customer binding and staff invite entries', () => {
  const source = fs.readFileSync(path.join(root, 'pages/profile/index.js'), 'utf8')
  assert.match(source, /id:\s*['"]promote-code['"]/) // 业务员患者绑定码
  assert.match(source, /id:\s*['"]staff-invite['"]/) // 仅组织管理员可见
  assert.match(source, /id:\s*['"]article-list['"]/) // 其他服务保留
  assert.match(source, /title:\s*['"]文章资讯['"]/)
  assert.match(source, /description:\s*['"]阅读最新内容['"]/)
  assert.match(source, /profile-article-icon\.png/)
  assert.ok(source.indexOf("id: 'article-list'") > source.indexOf("id: 'contribution-detail'"))
  assert.match(source, /adminOnly/)
  assert.match(source, /businessOnly/)
})

test('home article and banner states are independently isolated', () => {
  const source = fs.readFileSync(path.join(root, 'pages/home/index.js'), 'utf8')
  assert.match(source, /articleState:\s*['"]loading['"]/)
  assert.match(source, /articleItems:\s*\[\]/)
  assert.match(source, /articleRequestVersion/)
  assert.match(source, /listArticles\(\{\s*limit:\s*6\s*\}\)/)
  assert.match(source, /listArticles\(\{\s*category:\s*['"]关于儒泰['"],\s*limit:\s*3\s*\}\)/)
  assert.match(source, /listArticles\(\{\s*category:\s*['"]心脑维养['"],\s*limit:\s*3\s*\}\)/)
  assert.match(source, /aboutSupportingItems/)
  assert.match(source, /wellnessSupportingItems/)
  assert.match(source, /\.slice\(0,\s*3\)/)
  assert.match(source, /version\s*!==\s*this\.articleRequestVersion/)
  assert.match(source, /bannerState:\s*['"]loading['"]/)
  assert.match(source, /bannerRequestVersion/)
})

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function loadHome(articleService, bannerService = { listBanners() { return Promise.resolve({ items: [] }) } }) {
  const pagePath = path.join(root, 'pages/home/index.js')
  const moduleStubs = {
    [path.join(root, 'services/article-service.js')]: articleService,
    [path.join(root, 'services/banner-service.js')]: bannerService,
    [path.join(root, 'services/session-service.js')]: {
      getCurrentSession() { return { userId: 'u1', role: 'promoter', activationStatus: 'active' } },
      getEntry() { return { type: 'stay' } }
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

test('article request failure does not affect the rest of the home content', async () => {
  const fixture = loadHome({
    listArticles() { return Promise.reject({ kind: 'NETWORK', message: '文章网络异常' }) }
  })
  try {
    fixture.page.onShow()
    await flush()
    await flush()
    assert.equal(fixture.page.data.articleState, 'recoverable-error')
    assert.equal(fixture.page.data.bannerState, 'empty')
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

test('home keeps three classified articles separate from health article cards', async () => {
  const calls = []
  const fixture = loadHome({
    listArticles(options) {
      calls.push(options)
      if (options.category === '关于儒泰') {
        return Promise.resolve({
          items: [
            { articleId: '4', title: '关于儒泰', summary: '介绍', category: '关于儒泰', viewCount: 0 },
            { articleId: '5', title: '儒泰服务', summary: '服务', category: '关于儒泰', viewCount: 0 },
            { articleId: '6', title: '儒泰故事', summary: '故事', category: '关于儒泰', viewCount: 0 }
          ],
          nextCursor: null,
          hasMore: false
        })
      }
      if (options.category === '心脑维养') {
        return Promise.resolve({
          items: [
            { articleId: '7', title: '心脑重点', category: '心脑维养', viewCount: 0 },
            { articleId: '8', title: '心脑习惯', category: '心脑维养', viewCount: 0 },
            { articleId: '9', title: '心脑阅读', category: '心脑维养', viewCount: 0 }
          ],
          nextCursor: null,
          hasMore: false
        })
      }
      return Promise.resolve({
        items: [
          { articleId: '4', title: '关于儒泰', category: '关于儒泰', viewCount: 0 },
          { articleId: '3', title: '心脑健康', category: '心脑维养', viewCount: 0 },
          { articleId: '2', title: '健康资讯', category: '健康资讯', viewCount: 0 }
        ],
        nextCursor: null,
        hasMore: false
      })
    }
  })
  try {
    fixture.page.onShow()
    await flush()
    await flush()
    assert.deepEqual(calls, [
      { limit: 6 },
      { category: '关于儒泰', limit: 3 },
      { category: '心脑维养', limit: 3 }
    ])
    assert.deepEqual(fixture.page.data.aboutSupportingItems.map((item) => item.articleId), ['5', '6'])
    assert.equal(fixture.page.data.aboutLead.articleId, '4')
    assert.equal(fixture.page.data.wellnessLead.articleId, '7')
    assert.deepEqual(fixture.page.data.wellnessSupportingItems.map((item) => item.articleId), ['8', '9'])
    assert.deepEqual(fixture.page.data.articleItems.map((item) => item.articleId), ['3', '2'])
  } finally {
    fixture.restore()
  }
})

test('banner request failure does not affect the article section', async () => {
  const fixture = loadHome(
    { listArticles() { return Promise.resolve({ items: [], nextCursor: null, hasMore: false }) } },
    { listBanners() { return Promise.reject({ kind: 'NETWORK', message: '轮播图网络异常' }) } }
  )
  try {
    fixture.page.onShow()
    await flush()
    await flush()
    assert.equal(fixture.page.data.bannerState, 'recoverable-error')
    assert.equal(fixture.page.data.articleState, 'empty')
    assert.deepEqual(fixture.page.data.bannerItems, [])
  } finally {
    fixture.restore()
  }
})

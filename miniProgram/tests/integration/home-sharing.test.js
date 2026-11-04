const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { createRequire } = require('node:module')

const root = path.resolve(__dirname, '../..')
const pagePath = path.join(root, 'pages/home/index.js')
const title = '儒泰医联｜让健康知识，走进日常'
const friendImage = '/assets/images/home-share-friend-v1.jpg'
const timelineImage = '/assets/images/home-share-timeline-v1.jpg'

function loadHome() {
  let definition
  const menus = []
  const realRequire = createRequire(pagePath)
  const stubs = {
    '../../services/session-service': {
      getCurrentSession() { return { role: 'guest' } },
      getEntry() { return { type: 'stay' } }
    },
    '../../services/article-service': {
      listArticles() { return Promise.reject(new Error('文章请求失败')) }
    },
    '../../services/banner-service': {
      listBanners() { return Promise.reject(new Error('轮播请求失败')) }
    },
    '../../services/navigation-service': { updateTabBar() {} }
  }
  vm.runInNewContext(fs.readFileSync(pagePath, 'utf8'), {
    require(id) { return stubs[id] || realRequire(id) },
    Page(value) { definition = value },
    wx: { showShareMenu(options) { menus.push(JSON.parse(JSON.stringify(options))) } }
  }, { filename: pagePath })
  const page = {
    ...definition,
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(values) { Object.assign(this.data, values) }
  }
  return { page, menus }
}

function plain(value) {
  return JSON.parse(JSON.stringify(value))
}

test('home enables friend and Moments sharing for guests on entry', () => {
  const { page, menus } = loadHome()
  page.onLoad()
  assert.deepEqual(menus, [{ menus: ['shareAppMessage', 'shareTimeline'] }])
})

test('home friend share uses a public home path and the branded landscape cover', () => {
  const { page } = loadHome()
  assert.deepEqual(plain(page.onShareAppMessage()), {
    title, path: '/pages/home/index', imageUrl: friendImage
  })
  assert.ok(require('../../app.json').pages.includes('pages/home/index'))
})

test('home Moments share uses the square cover and clears incoming query parameters', () => {
  const { page } = loadHome()
  assert.deepEqual(plain(page.onShareTimeline()), {
    title, query: '', imageUrl: timelineImage
  })
})

test('sharing stays available after content failures and never includes account or binding data', async () => {
  const { page } = loadHome()
  page.data.session = { userId: 'private-user', token: 'private-token', refToken: 'private-ref' }
  await Promise.all([page.loadArticles(), page.loadBanners()])
  assert.equal(page.data.articleState, 'recoverable-error')
  assert.equal(page.data.bannerState, 'recoverable-error')
  for (const state of ['loading', 'empty', 'recoverable-error', 'success']) {
    page.data.articleState = state
    assert.deepEqual(plain(page.onShareAppMessage()), {
      title, path: '/pages/home/index', imageUrl: friendImage
    })
    assert.deepEqual(plain(page.onShareTimeline()), {
      title, query: '', imageUrl: timelineImage
    })
  }
})

test('both share covers are packaged local JPEGs with a small combined footprint', () => {
  let totalBytes = 0
  for (const image of [friendImage, timelineImage]) {
    const bytes = fs.readFileSync(path.join(root, image))
    assert.equal(bytes.readUInt16BE(0), 0xffd8)
    totalBytes += bytes.length
  }
  assert.ok(totalBytes < 150 * 1024, `分享图片合计 ${totalBytes} bytes`)
})

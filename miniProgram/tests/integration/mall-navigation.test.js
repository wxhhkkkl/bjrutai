const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const miniRoot = path.resolve(__dirname, '../..')

function read(relativePath) {
  return fs.readFileSync(path.join(miniRoot, relativePath), 'utf8')
}

function loadProfile(overrides = {}) {
  const pagePath = path.join(miniRoot, 'pages/profile/index.js')
  const originalPage = global.Page
  const originalWx = global.wx
  const originalPages = global.getCurrentPages
  const saved = new Map()
  let definition

  Object.entries(overrides).forEach(([modulePath, exports]) => {
    const resolved = path.join(miniRoot, modulePath)
    saved.set(resolved, require.cache[resolved])
    require.cache[resolved] = { id: resolved, filename: resolved, loaded: true, exports }
  })

  global.Page = (value) => { definition = value }
  global.getCurrentPages = () => [{}]
  global.wx = {
    navigateTo() {},
    reLaunch() {},
    switchTab() {},
    stopPullDownRefresh() {}
  }
  delete require.cache[pagePath]
  require(pagePath)

  const page = Object.assign({}, definition, {
    data: { ...definition.data },
    setData(values, callback) {
      this.data = Object.assign({}, this.data, values)
      if (callback) callback()
    }
  })

  return {
    page,
    restore() {
      delete require.cache[pagePath]
      saved.forEach((value, resolved) => {
        if (value) require.cache[resolved] = value
        else delete require.cache[resolved]
      })
      global.Page = originalPage
      global.wx = originalWx
      global.getCurrentPages = originalPages
    }
  }
}

test('mall journeys are registered while the five primary tabs stay unchanged', () => {
  const app = JSON.parse(read('app.json'))
  const mallRoutes = [
    'pages/mall/index',
    'pages/mall-product/index',
    'pages/mall-cart/index',
    'pages/mall-address/index',
    'pages/mall-checkout/index',
    'pages/mall-payment-result/index',
    'pages/mall-orders/index',
    'pages/mall-order-detail/index',
    'pages/mall-invoice-apply/index',
    'pages/mall-invoice-detail/index',
    'pages/mall-aftersale-apply/index',
    'pages/mall-aftersale-detail/index',
    'pages/mall-return-shipment/index',
    'pages/mall-logistics/index'
  ]
  mallRoutes.forEach((route) => assert.ok(app.pages.includes(route), `missing ${route}`))
  assert.equal(app.tabBar.custom, true)
  assert.deepEqual(app.tabBar.list.map((item) => item.pagePath), [
    'pages/home/index',
    'pages/customers/index',
    'pages/internet-hospital/index',
    'pages/mall/index',
    'pages/profile/index'
  ])
})

test('profile keeps a direct Mall orders entry usable when the account summary fails', async () => {
  const session = {
    userId: 'buyer-17',
    name: '商城买家',
    profileCompleted: true,
    hasBusinessMembership: false
  }
  const navigation = []
  const fixture = loadProfile({
    'services/session-service.js': {
      getCurrentSession: () => session,
      getAccessToken: () => 'buyer-token',
      getEntry: () => ({ type: 'tab' })
    },
    'services/workbench-service.js': {
      getWorkbench: async () => null,
      getAccountSummary: async () => { throw new Error('账户摘要暂时不可用') }
    },
    'services/navigation-service.js': {
      updateTabBar() {},
      openAction(id) {
        return id === 'mall-orders'
          ? { ok: true, url: '/pages/mall-orders/index' }
          : { ok: false, message: '当前账号暂不可使用此功能' }
      }
    },
    'services/auth-service.js': { logoutAndClear: async () => {} },
    'models/workbench.js': {
      adaptWorkbench: (value) => value,
      adaptAccountSummary: (value) => value,
      buildProfileViewModel: () => []
    },
    'models/collaborator.js': { getIdentityLabel: () => '普通用户' }
  })
  const originalWx = global.wx
  global.wx = {
    navigateTo: (options) => navigation.push(options.url),
    reLaunch() {},
    switchTab() {}
  }

  try {
    fixture.page.onShow()
    await new Promise((resolve) => setImmediate(resolve))
    assert.equal(fixture.page.data.state, 'recoverable-error')
    fixture.page.action({ currentTarget: { dataset: { id: 'mall-orders' } } })
    assert.deepEqual(navigation, ['/pages/mall-orders/index'])

    const markup = read('pages/profile/index.wxml')
    const entryPosition = markup.indexOf('profile-mall-entry')
    const successOnlyPosition = markup.indexOf('<block wx:if="{{state === \'success\'}}">')
    assert.ok(entryPosition >= 0)
    assert.ok(successOnlyPosition > entryPosition, 'order entry must render outside summary success state')
  } finally {
    global.wx = originalWx
    fixture.restore()
  }
})

test('profile refresh, page state announcement, keyboard positioning and bottom safe areas are explicit', async () => {
  let refreshedSession = null
  let stoppedRefresh = false
  const session = { userId: 'buyer-17', profileCompleted: true }
  const originalWx = global.wx
  const fixture = loadProfile({
    'services/session-service.js': {
      getCurrentSession: () => session,
      getAccessToken: () => 'buyer-token',
      getEntry: () => ({ type: 'tab' })
    },
    'services/workbench-service.js': { getWorkbench: async () => null, getAccountSummary: async () => ({ userId: 'buyer-17' }) },
    'services/navigation-service.js': { updateTabBar() {}, openAction: () => ({ ok: false }) },
    'services/auth-service.js': { logoutAndClear: async () => {} },
    'models/workbench.js': { adaptWorkbench: (value) => value, adaptAccountSummary: (value) => value, buildProfileViewModel: () => [] },
    'models/collaborator.js': { getIdentityLabel: () => '普通用户' }
  })
  global.wx = { stopPullDownRefresh() { stoppedRefresh = true } }

  try {
    fixture.page.loadProfile = async (value) => { refreshedSession = value }
    await fixture.page.onPullDownRefresh()
    assert.equal(refreshedSession, session)
    assert.equal(stoppedRefresh, true)

    const profileJson = JSON.parse(read('pages/profile/index.json'))
    assert.equal(profileJson.enablePullDownRefresh, true)
    assert.match(read('components/page-state/index.wxml'), /aria-role="\{\{state === 'recoverable-error' \|\| state === 'forbidden' \? 'alert' : 'status'\}\}"/)
    assert.match(read('pages/profile/index.wxss'), /env\(safe-area-inset-bottom\)/)
    assert.match(read('custom-tab-bar/index.wxss'), /env\(safe-area-inset-bottom\)/)
    assert.match(read('app.wxss'), /\.tab-screen[\s\S]*env\(safe-area-inset-bottom\)/)

    const formPaths = [
      'pages/mall/index.wxml',
      'pages/mall-address/index.wxml',
      'pages/mall-checkout/index.wxml',
      'pages/mall-invoice-apply/index.wxml',
      'pages/mall-invoice-detail/index.wxml',
      'pages/mall-aftersale-apply/index.wxml',
      'pages/mall-return-shipment/index.wxml'
    ]
    for (const relativePath of formPaths) {
      const markup = read(relativePath)
      const fields = markup.match(/<(?:input|textarea)\b[^>]*>/g) || []
      assert.ok(fields.length, `${relativePath} should contain a form field`)
      fields.forEach((field) => {
        assert.match(field, /adjust-position="true"/, `${relativePath}: keyboard should adjust the viewport`)
        assert.match(field, /cursor-spacing="80"/, `${relativePath}: keep the focused field above the keyboard`)
        if (/focus="\{\{focusField === '[^']+'\}\}"/.test(field)) {
          assert.match(field, /bindblur="[A-Za-z]+"/, `${relativePath}: a focus-bound field must clear its focus state on blur`)
        }
      })
      if (!['pages/mall/index.wxml', 'pages/mall-checkout/index.wxml'].includes(relativePath)) {
        assert.match(markup, /scroll-into-view="\{\{errorTarget\}\}"/, `${relativePath}: validation should scroll its first target into view`)
      }
    }

    const formErrorPage = {
      data: {},
      setData(values, callback) {
        this.data = Object.assign({}, this.data, values)
        if (callback) callback()
      }
    }
    const formError = require('../../utils/mall-form-error')
    formError.setMallFormError(formErrorPage, '请填写发票抬头', { field: 'title' })
    assert.equal(formErrorPage.data.focusField, 'title')
    assert.equal(formErrorPage.data.errorTarget, 'mall-field-title')
    assert.equal(formErrorPage.data.stateMessage, '请填写发票抬头')
    assert.match(read('pages/mall-invoice-apply/index.wxml'), /focus="\{\{focusField === 'title'\}\}"/)
    assert.match(read('pages/mall-address/index.wxml'), /focus="\{\{focusField === 'recipientName'\}\}"/)
    assert.match(read('pages/mall-aftersale-apply/index.wxml'), /focus="\{\{focusField === 'reason'\}\}"/)
    assert.match(read('pages/mall-return-shipment/index.wxml'), /focus="\{\{focusField === 'trackingNo'\}\}"/)
    formError.clearMallFormError(formErrorPage)
    assert.equal(formErrorPage.data.focusField, '')
    assert.equal(formErrorPage.data.errorTarget, '')
  } finally {
    global.wx = originalWx
    fixture.restore()
  }
})

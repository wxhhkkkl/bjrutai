const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function loadPage(relativePath, replacements = {}) {
  const root = path.resolve(__dirname, '../..')
  const pagePath = path.resolve(root, relativePath)
  const originalPage = global.Page
  const originalWx = global.wx
  const originalPages = global.getCurrentPages
  const saved = new Map()
  Object.entries(replacements).forEach(([modulePath, exports]) => {
    const resolved = path.resolve(root, modulePath)
    saved.set(resolved, require.cache[resolved])
    require.cache[resolved] = { id: resolved, filename: resolved, loaded: true, exports }
  })
  let definition
  const navigation = []
  const modals = []
  global.Page = (value) => { definition = value }
  global.getCurrentPages = () => [{}]
  global.wx = {
    navigateTo(options) { navigation.push(['navigateTo', options.url]) },
    redirectTo(options) { navigation.push(['redirectTo', options.url]) },
    navigateBack(options = {}) { navigation.push(['navigateBack', options.delta || 1]) },
    switchTab(options) { navigation.push(['switchTab', options.url]) },
    showToast(options) { navigation.push(['toast', options.title]) },
    showModal(options) { modals.push(options); options.success({ confirm: true, cancel: false }) },
    stopPullDownRefresh() {},
    setStorageSync() {},
    getStorageSync() { return null },
    removeStorageSync() {}
  }
  delete require.cache[pagePath]
  require(pagePath)
  const page = Object.assign({}, definition, {
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(values, callback) {
      this.data = Object.assign({}, this.data, values)
      if (callback) callback()
    }
  })
  return {
    page,
    navigation,
    modals,
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

test('orders page filters by server status, pages by opaque cursor and recovers errors', async () => {
  const calls = []
  let fail = false
  const service = {
    listMyMallOrders: async (options) => {
      calls.push(options)
      if (fail) throw new Error('订单暂时不可用')
      if (options.cursor) return { items: [{ id: '30', orderNo: 'M30', status: 'completed', items: [], payableAmountCent: 0 }], nextCursor: null, total: 2 }
      return { items: [{ id: '31', orderNo: 'M31', status: options.status || 'pending_payment', items: [{ productName: '健康商品', quantity: 1 }], payableAmountCent: 990 }], nextCursor: 'opaque-page-2', total: 2 }
    }
  }
  const fixture = loadPage('pages/mall-orders/index.js', {
    'services/mall-order-service.js': service,
    'services/session-service.js': { getAccessToken: () => 'buyer-token' }
  })
  try {
    await fixture.page.onLoad()
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.orders[0].amountText, '9.90')
    fixture.page.selectStatus({ currentTarget: { dataset: { status: 'pending_receipt' } } })
    await flush()
    assert.deepEqual(calls.at(-1), { status: 'pending_receipt', pageSize: 20 })
    fixture.page.onReachBottom()
    await flush()
    assert.equal(fixture.page.data.orders.length, 2)
    assert.equal(calls.at(-1).cursor, 'opaque-page-2')
    fail = true
    fixture.page.selectStatus({ currentTarget: { dataset: { status: 'closed' } } })
    await flush()
    assert.equal(fixture.page.data.state, 'recoverable-error')
    assert.equal(fixture.page.data.orders.length, 0)
  } finally { fixture.restore() }
})

test('order detail uses backend actions, confirms receipt once and opens the logistics snapshot', async () => {
  const calls = []
  const order = {
    id: '31', orderNo: 'M31', status: 'pending_receipt', version: 4,
    paymentStatus: 'succeeded', payableAmountCent: 990, goodsAmountCent: 990,
    freightAmountCent: 0, items: [{ productName: '健康商品', optionsText: '标准装', quantity: 1, unitPriceCent: 990 }],
    address: { recipientName: '买家', phoneMasked: '138****8000', addressMasked: '详细地址已保存' },
    shipment: { id: '9', courierCode: 'zto', trackingNo: '1234567890', platformSyncStatus: 'unknown', version: 2 },
    availableActions: ['confirmMallReceipt'], timeline: []
  }
  const service = {
    getMyMallOrder: async (id) => { calls.push(['get', id]); return order },
    confirmMallReceipt: async (...args) => { calls.push(['confirm', ...args]); return order }
  }
  const fixture = loadPage('pages/mall-order-detail/index.js', {
    'services/mall-order-service.js': service,
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-receipt-page-key-0001' },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' }
  })
  try {
    await fixture.page.onLoad({ id: '31' })
    await flush()
    assert.equal(fixture.page.data.order.status, 'pending_receipt')
    assert.equal(fixture.page.data.order.amountText, '9.90')
    fixture.page.openLogistics()
    assert.deepEqual(fixture.navigation.at(-1), ['navigateTo', '/pages/mall-logistics/index?id=31'])
    await fixture.page.confirmReceipt()
    assert.equal(fixture.modals.length, 1)
    assert.deepEqual(calls.find((call) => call[0] === 'confirm'), ['confirm', '31', 4, 'mall-receipt-page-key-0001'])
    assert.ok(calls.filter((call) => call[0] === 'get').length >= 2)
  } finally { fixture.restore() }
})

test('logistics page keeps provider source and platform receipt as separate facts', async () => {
  const calls = []
  const service = {
    getMyMallLogistics: async (id) => {
      calls.push(id)
      return { orderId: id, source: null, queryStatus: 'config_required', events: [], mapAvailable: false, stateName: null }
    }
  }
  const fixture = loadPage('pages/mall-logistics/index.js', {
    'services/mall-order-service.js': service,
    'services/session-service.js': { getAccessToken: () => 'buyer-token' }
  })
  try {
    await fixture.page.onLoad({ id: '31' })
    await flush()
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.sourceLabel, '尚未查询到真实物流轨迹')
    assert.equal(fixture.page.data.snapshot.queryStatus, 'config_required')
    await fixture.page.refresh()
    assert.deepEqual(calls, ['31', '31'])
    const markup = fs.readFileSync(path.resolve(__dirname, '../../pages/mall-logistics/index.wxml'), 'utf8')
    assert.match(markup, /不代表平台确认收货/)
  } finally { fixture.restore() }
})

test('mall order routes and the profile entry preserve five primary tabs', () => {
  const root = path.resolve(__dirname, '../..')
  const app = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'))
  const navigation = require('../../models/navigation')
  for (const route of ['pages/mall-orders/index', 'pages/mall-order-detail/index', 'pages/mall-logistics/index']) {
    assert.ok(app.pages.includes(route), `missing ${route}`)
  }
  assert.equal(app.tabBar.list.length, 5)
  assert.equal(navigation.ACTION_TARGETS['mall-orders'].path, '/pages/mall-orders/index')
  const profile = fs.readFileSync(path.join(root, 'pages/profile/index.js'), 'utf8')
  const profileMarkup = fs.readFileSync(path.join(root, 'pages/profile/index.wxml'), 'utf8')
  assert.match(profileMarkup, /data-id="mall-orders"/)
  assert.match(profileMarkup, /class="profile-mall-entry/)
  assert.doesNotMatch(profile, /id: 'mall-orders'/)
})

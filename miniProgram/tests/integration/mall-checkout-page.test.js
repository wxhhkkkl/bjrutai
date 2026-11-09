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
  global.Page = (value) => { definition = value }
  global.getCurrentPages = () => [{}]
  global.wx = {
    navigateTo(options) { navigation.push(['navigateTo', options.url]) },
    redirectTo(options) { navigation.push(['redirectTo', options.url]) },
    navigateBack(options = {}) { navigation.push(['navigateBack', options.delta || 1]) },
    switchTab(options) { navigation.push(['switchTab', options.url]) },
    showToast(options) { navigation.push(['toast', options.title]) },
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

test('cart continues only valid selected SKUs and saves a PII-free checkout draft', async () => {
  const drafts = []
  const service = {
    getCheckoutSettings: async () => ({ purchasingAvailable: true }),
    getCart: async () => ({ items: [
      { id: '1', sku: { id: '11', priceCent: 500, options: [] }, productName: '商品甲', quantity: 2, valid: true, version: 1 },
      { id: '2', sku: { id: '12', priceCent: 800, options: [] }, productName: '失效商品', quantity: 1, valid: false, invalidReason: 'sold_out', version: 1 }
    ] }),
    updateCartItem: async () => ({}),
    removeCartItem: async () => ({})
  }
  const intent = {
    getPendingIntent: () => null,
    saveCheckoutDraft(value) { drafts.push(value) }
  }
  const fixture = loadPage('pages/mall-cart/index.js', {
    'services/mall-checkout-service.js': service,
    'services/mall-intent-service.js': intent,
    'services/session-service.js': { getAccessToken: () => 'buyer-token', getCurrentSession: () => ({ userId: 'buyer-1' }) }
  })
  try {
    await fixture.page.onLoad()
    assert.equal(fixture.page.data.items.length, 2)
    assert.deepEqual(fixture.page.data.selectedIds, ['1'])
    fixture.page.continueCheckout()
    assert.deepEqual(drafts[0], { items: [{ skuId: '11', quantity: 2 }], source: 'cart' })
    assert.deepEqual(fixture.navigation.at(-1), ['navigateTo', '/pages/mall-checkout/index'])
  } finally { fixture.restore() }
})

test('checkout obtains a server quote and records invoice intent only with order creation', async () => {
  const calls = []
  const orderSubmissions = []
  let savedSubmission = null
  const intent = {
    getCheckoutDraft: () => ({ items: [{ skuId: '11', quantity: 2 }], addressId: '', source: 'cart', userId: 'buyer-1' }),
    getPendingIntent: () => null,
    getOrderSubmission: () => savedSubmission,
    createIdempotencyKey: () => 'mall-order-idempotency-test-0001',
    saveOrderSubmission(value) { savedSubmission = value; orderSubmissions.push(value) },
    clearOrderSubmission() {},
    clearCheckoutDraft() {},
    clearPendingIntent() {},
    savePendingOrder() {}
  }
  const service = {
    getCheckoutSettings: async () => ({ purchasingAvailable: true, freightMode: 'fixed', freightCent: 1200, policyVersion: 'policy-v3' }),
    listAddresses: async () => ({ items: [{ id: '8', recipientName: '买家', phoneMasked: '138****8000', addressMasked: '详细地址已保存', isDefault: true, version: 1 }] }),
    quoteOrder: async (value) => { calls.push(['quote', value]); return { quoteToken: 'signed-quote', goodsAmountCent: 500, freightAmountCent: 1200, payableAmountCent: 1700, policyVersion: 'policy-v3', items: [] } },
    createOrder: async (value, key) => { calls.push(['create', value, key]); return { id: '31', status: 'pending_payment', version: 1 } }
  }
  const fixture = loadPage('pages/mall-checkout/index.js', {
    'services/mall-checkout-service.js': service,
    'services/mall-intent-service.js': intent,
    'services/session-service.js': { getAccessToken: () => 'buyer-token', getCurrentSession: () => ({ userId: 'buyer-1' }) }
  })
  try {
    await fixture.page.onLoad()
    await flush()
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.quote.payableAmountCent, 1700)
    fixture.page.setData({ invoiceIntent: true, purchaseConsent: true })
    await fixture.page.submitOrder()
    assert.deepEqual(calls[0], ['quote', { addressId: '8', items: [{ skuId: '11', quantity: 2 }] }])
    assert.equal(calls[1][1].invoiceIntent, true)
    assert.equal(calls[1][1].consentVersion, 'policy-v3')
    assert.equal(orderSubmissions.length, 1)
    assert.deepEqual(fixture.navigation.at(-1), ['redirectTo', '/pages/mall-payment-result/index?id=31'])
  } finally { fixture.restore() }
})

test('address form requires explicit purpose consent and retains picker labels', async () => {
  const saved = []
  const service = {
    getCheckoutSettings: async () => ({ policyVersion: 'policy-v3' }),
    listAddresses: async () => ({ items: [] }),
    createAddress: async (value, key) => { saved.push({ value, key }); return { id: '8' } }
  }
  const fixture = loadPage('pages/mall-address/index.js', {
    'services/mall-checkout-service.js': service,
    'services/mall-intent-service.js': { getCheckoutDraft: () => null, createIdempotencyKey: () => 'mall-address-key-test-0001' },
    'services/session-service.js': { getAccessToken: () => 'buyer-token', getCurrentSession: () => ({ userId: 'buyer-1' }) }
  })
  try {
    await fixture.page.onLoad({})
    fixture.page.showAddressForm()
    fixture.page.setData({ recipientName: '收件人', phone: '13800138000', addressLine: '北五环路1号' })
    fixture.page.onRegionChange({ detail: { code: ['110000', '110100', '110101'], value: ['北京市', '北京市', '东城区'] } })
    await fixture.page.saveAddress()
    assert.equal(saved.length, 0)
    assert.equal(fixture.page.data.errorTarget, 'mall-field-consent')
    fixture.page.toggleConsent()
    await fixture.page.saveAddress()
    assert.equal(saved.length, 1)
    assert.deepEqual(saved[0].value.regionCodes, ['110000', '110100', '110101'])
    assert.deepEqual(saved[0].value.regionNames, ['北京市', '北京市', '东城区'])
    assert.equal(saved[0].value.consentConfirmed, true)
    assert.equal(saved[0].value.consentVersion, 'policy-v3')
    assert.match(saved[0].key, /mall/)
  } finally { fixture.restore() }
})

test('payment result keeps a cancelled client attempt unpaid and offers original-order query', async () => {
  const calls = []
  const payment = {
    reconcilePayment: async (id) => { calls.push(['query', id]); return { status: 'pending', order: { id, status: 'pending_payment', version: 1 }, payment: { status: 'pending' } } },
    payOrder: async (id) => { calls.push(['pay', id]); return { status: 'pending', requestPaymentOutcome: 'cancelled', order: { id, status: 'pending_payment', version: 1 }, payment: { status: 'pending' } } }
  }
  const fixture = loadPage('pages/mall-payment-result/index.js', {
    'services/mall-payment-service.js': payment,
    'services/mall-intent-service.js': { clearPendingOrder() {}, clearOrderSubmission() {} },
    'services/session-service.js': { getAccessToken: () => 'buyer-token', getCurrentSession: () => ({ userId: 'buyer-1' }) }
  })
  try {
    await fixture.page.onLoad({ id: '31' })
    await fixture.page.continuePayment()
    assert.equal(fixture.page.data.state, 'pending')
    assert.match(fixture.page.data.message, /取消本次支付|仍待支付/)
    assert.deepEqual(calls.at(-1), ['pay', '31'])
    await fixture.page.queryPayment()
    assert.equal(calls.at(-1)[0], 'query')
    assert.equal(fixture.page.data.state, 'pending')
  } finally { fixture.restore() }
})

test('checkout routes are registered and the mall keeps the provided no-combined-tab layout', () => {
  const app = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../app.json'), 'utf8'))
  for (const page of [
    'pages/mall-cart/index',
    'pages/mall-address/index',
    'pages/mall-checkout/index',
    'pages/mall-payment-result/index'
  ]) assert.ok(app.pages.includes(page), `missing ${page}`)
  const mall = fs.readFileSync(path.resolve(__dirname, '../../pages/mall/index.wxml'), 'utf8')
  assert.doesNotMatch(mall, /综合/)
})

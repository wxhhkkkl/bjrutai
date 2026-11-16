const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

function loadPage(relativePath, replacements = {}, wxOverrides = {}) {
  const root = path.resolve(__dirname, '../..')
  const pagePath = path.resolve(root, relativePath)
  const originalPage = global.Page
  const originalWx = global.wx
  const originalPages = global.getCurrentPages
  const saved = new Map()
  const navigation = []
  const modals = []
  Object.entries(replacements).forEach(([modulePath, exports]) => {
    const resolved = path.resolve(root, modulePath)
    saved.set(resolved, require.cache[resolved])
    require.cache[resolved] = { id: resolved, filename: resolved, loaded: true, exports }
  })
  let definition
  global.Page = (value) => { definition = value }
  global.getCurrentPages = () => [{}]
  global.wx = {
    navigateTo(options) { navigation.push(['navigateTo', options.url]) },
    redirectTo(options) { navigation.push(['redirectTo', options.url]) },
    navigateBack(options = {}) { navigation.push(['navigateBack', options.delta || 1]) },
    showToast(options) { navigation.push(['toast', options.title]) },
    showModal(options) { modals.push(options); options.success({ confirm: true, cancel: false }) },
    chooseImage(options) {
      options.success({
        tempFilePaths: ['/tmp/aftersale.jpg'],
        tempFiles: [{ path: '/tmp/aftersale.jpg', size: 3 }]
      })
    },
    stopPullDownRefresh() {},
    ...wxOverrides
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

const order = {
  id: '31',
  version: 7,
  status: 'pending_shipment',
  freightAmountCent: 1000,
  invoiceStatus: 'not_requested',
  items: [
    { id: '101', productName: '健康食品', optionsText: '标准装', quantity: 2, lineAmountCent: 3000, availableAftersaleQuantity: 2 },
    { id: '102', productName: '滋养饮品', optionsText: '', quantity: 1, lineAmountCent: 5000, availableAftersaleQuantity: 0 }
  ],
  aftersaleIds: []
}

function applyDependencies(options = {}) {
  return {
    'services/mall-order-service.js': { getMyMallOrder: async () => options.order || order },
    'services/mall-aftersale-service.js': {
      createMallAftersale: options.createMallAftersale || (async () => ({ id: '51', version: 1, status: 'submitted' })),
      computeProofSha256: async () => 'proof-sha256-digest',
      getAftersaleProofUploadTicket: async () => ({ fileId: '71', uploadUrl: 'https://bucket-1.cos.ap-beijing.myqcloud.com/mall/proof?signature=temporary' }),
      uploadAftersaleProofFile: async () => ({ statusCode: 204 }),
      verifyAftersaleProof: async () => ({ id: '71', status: 'verified', version: 2 })
    },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-aftersale-action-0001' }
  }
}

test('order detail exposes the aftersale entry and links existing records', async () => {
  const mallOrderService = {
    getMyMallOrder: async () => ({ ...order, aftersaleIds: ['51'] })
  }
  const fixture = loadPage('pages/mall-order-detail/index.js', {
    'services/mall-order-service.js': mallOrderService,
    'services/mall-aftersale-service.js': { getMyMallAftersale: async () => ({ id: '51' }) },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-receipt-page-key-0001' },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'utils/request-key.js': { createRequestKeyManager: () => ({ begin: () => 'mall-receipt-page-key-0001', markSucceeded() {}, markUnknown() {} }) }
  })
  try {
    await fixture.page.onLoad({ id: '31' })
    assert.equal(fixture.page.data.order.canApplyAftersale, true)
    assert.equal(fixture.page.data.order.invoiceStatusLabel, '未申请')
    fixture.page.openAftersale()
    assert.deepEqual(fixture.navigation.at(-1), ['navigateTo', '/pages/mall-aftersale-apply/index?orderId=31'])
    fixture.page.openAftersaleRecord({ currentTarget: { dataset: { id: '51' } } })
    assert.deepEqual(fixture.navigation.at(-1), ['navigateTo', '/pages/mall-aftersale-detail/index?id=51'])
    const markup = fs.readFileSync(path.join(__dirname, '../../pages/mall-order-detail/index.wxml'), 'utf8')
    assert.match(markup, /申请售后/)
    assert.match(markup, /aftersaleRecords/)
  } finally { fixture.restore() }
})

test('application loads the server snapshot, constrains item quantity and submits a stable request', async () => {
  const calls = []
  const fixture = loadPage('pages/mall-aftersale-apply/index.js', applyDependencies({
    createMallAftersale: async (...args) => { calls.push(args); return { id: '51', version: 1, status: 'submitted' } }
  }))
  try {
    await fixture.page.onLoad({ orderId: '31' })
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.order.items[1].availableAftersaleQuantity, 0)
    fixture.page.selectScope({ currentTarget: { dataset: { scope: 'freight_only' } } })
    assert.equal(fixture.page.data.scope, 'freight_only')
    fixture.page.selectScope({ currentTarget: { dataset: { scope: 'goods' } } })
    fixture.page.selectMethod({ currentTarget: { dataset: { method: 'return_refund' } } })
    assert.equal(fixture.page.data.method, 'refund_only')
    fixture.page.changeQuantity({ currentTarget: { dataset: { id: '101', delta: '1' } } })
    fixture.page.changeQuantity({ currentTarget: { dataset: { id: '102', delta: '1' } } })
    await fixture.page.submitApplication()
    assert.equal(fixture.page.data.focusField, 'reason')
    assert.equal(fixture.page.data.errorTarget, 'mall-field-reason')
    fixture.page.onReasonInput({ detail: { value: '商品外包装破损' } })
    await fixture.page.submitApplication()

    assert.equal(calls.length, 1)
    assert.deepEqual(calls[0][0], {
      orderId: '31', expectedOrderVersion: 7, method: 'refund_only', scope: 'goods',
      items: [{ orderItemId: '101', quantity: 1 }], reason: '商品外包装破损',
      proofFileIds: []
    })
    assert.equal(calls[0][1], 'mall-aftersale-action-0001')
    assert.deepEqual(fixture.navigation.at(-1), ['redirectTo', '/pages/mall-aftersale-detail/index?id=51'])
    assert.equal(fixture.modals.length, 1)
  } finally { fixture.restore() }
})

test('unshipped orders offer refund-only while shipped orders still allow return refund', async () => {
  const unshipped = loadPage('pages/mall-aftersale-apply/index.js', applyDependencies())
  try {
    await unshipped.page.onLoad({ orderId: '31' })
    assert.deepEqual(unshipped.page.data.methods.map((item) => item.value), ['refund_only'])
    unshipped.page.selectMethod({ currentTarget: { dataset: { method: 'return_refund' } } })
    assert.equal(unshipped.page.data.method, 'refund_only')
  } finally { unshipped.restore() }

  const shipped = loadPage('pages/mall-aftersale-apply/index.js', applyDependencies({
    order: { ...order, status: 'pending_receipt', shipment: { id: '9' } }
  }))
  try {
    await shipped.page.onLoad({ orderId: '31' })
    assert.deepEqual(shipped.page.data.methods.map((item) => item.value), ['refund_only', 'return_refund'])
    shipped.page.selectMethod({ currentTarget: { dataset: { method: 'return_refund' } } })
    assert.equal(shipped.page.data.method, 'return_refund')
  } finally { shipped.restore() }
})

test('freight-only orders open with the only available scope selected', async () => {
  const fixture = loadPage('pages/mall-aftersale-apply/index', {
    ...applyDependencies(),
    'services/mall-order-service.js': {
      getMyMallOrder: async () => ({
        ...order, items: order.items.map((item) => ({ ...item, availableAftersaleQuantity: 0 })),
        refundReservedCent: 0, refundedFreightCent: 0
      })
    }
  })
  try {
    await fixture.page.onLoad({ orderId: '31' })
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.scope, 'freight_only')
    assert.equal(fixture.page.data.method, 'refund_only')
    assert.deepEqual(fixture.page.buildApplication().items, [])
  } finally { fixture.restore() }
})

test('uncertain application retries the same body with the original idempotency key', async () => {
  const calls = []
  const createMallAftersale = async (...args) => {
    calls.push(args)
    if (calls.length === 1) {
      const error = new Error('网络连接中断')
      error.kind = 'NETWORK'
      throw error
    }
    return { id: '52', version: 1, status: 'submitted' }
  }
  const fixture = loadPage('pages/mall-aftersale-apply/index.js', applyDependencies({ createMallAftersale }))
  try {
    await fixture.page.onLoad({ orderId: '31' })
    fixture.page.changeQuantity({ currentTarget: { dataset: { id: '101', delta: '1' } } })
    fixture.page.onReasonInput({ detail: { value: '申请原因' } })
    await fixture.page.submitApplication()
    assert.deepEqual(fixture.navigation.at(-1), ['toast', '网络连接中断'])
    await fixture.page.submitApplication()
    assert.equal(calls.length, 2)
    assert.deepEqual(calls[1], calls[0])
    assert.deepEqual(fixture.navigation.at(-1), ['redirectTo', '/pages/mall-aftersale-detail/index?id=52'])
  } finally { fixture.restore() }
})

test('proof photos are uploaded and verified before their IDs enter the application', async () => {
  const calls = []
  const dependencies = applyDependencies()
  const aftersaleService = dependencies['services/mall-aftersale-service.js']
  aftersaleService.getAftersaleProofUploadTicket = async (...args) => { calls.push(['ticket', ...args]); return { fileId: '71', uploadUrl: 'https://bucket-1.cos.ap-beijing.myqcloud.com/mall/proof?signature=temporary' } }
  aftersaleService.uploadAftersaleProofFile = async (...args) => { calls.push(['upload', ...args]); return { statusCode: 204 } }
  aftersaleService.verifyAftersaleProof = async (...args) => { calls.push(['verify', ...args]); return { id: '71', status: 'verified' } }
  const fixture = loadPage('pages/mall-aftersale-apply/index.js', dependencies)
  try {
    await fixture.page.onLoad({ orderId: '31' })
    await fixture.page.chooseProofImages()
    assert.deepEqual(fixture.page.data.proofFileIds, ['71'])
    assert.deepEqual(calls.map((call) => call[0]), ['ticket', 'upload', 'verify'])
    assert.equal(fixture.page.data.proofs[0].status, 'verified')
  } finally { fixture.restore() }
})

test('the same proof image is rejected instead of uploaded twice', async () => {
  const calls = []
  const dependencies = applyDependencies()
  const aftersaleService = dependencies['services/mall-aftersale-service.js']
  aftersaleService.getAftersaleProofUploadTicket = async (...args) => { calls.push(['ticket', ...args]); return { fileId: '71', uploadUrl: 'https://bucket-1.cos.ap-beijing.myqcloud.com/mall/proof?signature=temporary' } }
  aftersaleService.uploadAftersaleProofFile = async (...args) => { calls.push(['upload', ...args]); return { statusCode: 204 } }
  aftersaleService.verifyAftersaleProof = async (...args) => { calls.push(['verify', ...args]); return { id: '71', status: 'verified' } }
  const fixture = loadPage('pages/mall-aftersale-apply/index.js', dependencies)
  try {
    await fixture.page.onLoad({ orderId: '31' })
    await fixture.page.chooseProofImages()
    await fixture.page.chooseProofImages()
    assert.equal(calls.filter((call) => call[0] === 'ticket').length, 1)
    assert.deepEqual(fixture.page.data.proofFileIds, ['71'])
    assert.deepEqual(fixture.navigation.at(-1), ['toast', '这张图片已经添加过了'])
  } finally { fixture.restore() }
})

test('aftersale detail separates refund and invoice progress and opens the return form', async () => {
  const calls = []
  const aftersale = {
    id: '51', orderId: '31', aftersaleNo: 'AS-31-01', method: 'return_refund', status: 'awaiting_return',
    reason: '商品破损', goodsRefundCent: 3000, freightRefundCent: 0, refundId: null,
    returnInstructions: '退货地址：测试仓，电话：138****1234', returnTrackingNo: null, version: 3,
    items: [{ id: '71', quantity: 1, goodsRefundCent: 3000 }]
  }
  const fixture = loadPage('pages/mall-aftersale-detail/index.js', {
    'services/mall-aftersale-service.js': {
      getMyMallAftersale: async () => aftersale,
      getFinancialProgress: (value) => ({ aftersaleStatus: value.status, refundStatus: value.refundStatus || 'not_exposed', invoiceStatus: value.invoiceStatus || 'not_exposed' }),
      withdrawMallAftersale: async (...args) => { calls.push(args); return { ...aftersale, status: 'withdrawn', version: 4 } }
    },
    'services/mall-order-service.js': { getMyMallOrder: async () => ({ invoiceStatus: 'issued' }) },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-aftersale-action-0001' },
    'utils/request-key.js': { createRequestKeyManager: () => ({ begin: () => 'mall-aftersale-action-0001', markSucceeded() {}, markUnknown() {} }) }
  })
  try {
    await fixture.page.onLoad({ id: '51' })
    assert.equal(fixture.page.data.aftersale.statusLabel, '等待寄回')
    assert.equal(fixture.page.data.aftersale.refundStatusLabel, '状态未提供')
    assert.equal(fixture.page.data.aftersale.invoiceStatusLabel, '已开具')
    fixture.page.openReturnShipment()
    assert.deepEqual(fixture.navigation.at(-1), ['navigateTo', '/pages/mall-return-shipment/index?id=51'])
    const markup = fs.readFileSync(path.join(__dirname, '../../pages/mall-aftersale-detail/index.wxml'), 'utf8')
    assert.match(markup, /金额已核定也不等于退款到账/)
    assert.match(markup, /退款和发票是独立状态/)
  } finally { fixture.restore() }
})

test('aftersale detail pull-to-refresh reloads the snapshot and resets the refresher', async () => {
  let fetches = 0
  const aftersale = {
    id: '51', orderId: '31', method: 'refund_only', status: 'submitted',
    reason: '商品破损', goodsRefundCent: 3000, freightRefundCent: 0, version: 3,
    items: [{ id: '71', quantity: 1, goodsRefundCent: 3000 }]
  }
  const fixture = loadPage('pages/mall-aftersale-detail/index.js', {
    'services/mall-aftersale-service.js': {
      getMyMallAftersale: async () => { fetches += 1; return aftersale },
      getFinancialProgress: (value) => ({ aftersaleStatus: value.status, refundStatus: value.refundStatus || 'not_exposed', invoiceStatus: value.invoiceStatus || 'not_exposed' })
    },
    'services/mall-order-service.js': { getMyMallOrder: async () => ({ invoiceStatus: 'not_requested' }) },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-aftersale-action-0001' },
    'utils/request-key.js': { createRequestKeyManager: () => ({ begin: () => 'mall-aftersale-action-0001', markSucceeded() {}, markUnknown() {} }) }
  })
  try {
    await fixture.page.onLoad({ id: '51' })
    assert.equal(fixture.page.data.refreshing, false)
    const pending = fixture.page.refresh()
    assert.equal(fixture.page.data.refreshing, true)
    await pending
    assert.equal(fixture.page.data.refreshing, false)
    assert.equal(fetches, 2)
    const markup = fs.readFileSync(path.join(__dirname, '../../pages/mall-aftersale-detail/index.wxml'), 'utf8')
    assert.match(markup, /refresher-triggered="\{\{refreshing\}\}"/)
    assert.match(markup, /bindrefresherrefresh="refresh"/)
  } finally { fixture.restore() }
})

test('return shipment requires a valid carrier and tracking number then refreshes the detail', async () => {
  const calls = []
  const fixture = loadPage('pages/mall-return-shipment/index.js', {
    'services/mall-aftersale-service.js': {
      getMyMallAftersale: async () => ({
        id: '51', status: 'awaiting_return', version: 3,
        returnInstructions: '退货地址：测试仓，电话：138****1234'
      }),
      sendMallReturn: async (...args) => { calls.push(args); return { id: '51', status: 'awaiting_receipt', version: 4 } }
    },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-return-shipment-0001' },
    'utils/request-key.js': { createRequestKeyManager: () => ({ begin: () => 'mall-return-shipment-0001', markSucceeded() {}, markUnknown() {} }) }
  })
  try {
    await fixture.page.onLoad({ id: '51' })
    assert.equal(fixture.page.data.state, 'success')
    fixture.page.setData({ focusField: 'trackingNo' })
    fixture.page.onTrackingInput({ detail: { value: 'SF12345678' } })
    assert.equal(fixture.page.data.focusField, 'trackingNo')
    fixture.page.onTrackingBlur()
    assert.equal(fixture.page.data.focusField, '')
    await fixture.page.submitReturnShipment()
    assert.equal(calls.length, 0)
    assert.equal(fixture.page.data.errorTarget, 'mall-field-courier')
    fixture.page.onCourierChange({ detail: { value: 0 } })
    await fixture.page.submitReturnShipment()
    assert.deepEqual(calls, [['51', { expectedVersion: 3, courierCode: 'shunfeng', trackingNo: 'SF12345678' }, 'mall-return-shipment-0001']])
    assert.deepEqual(fixture.navigation.at(-1), ['redirectTo', '/pages/mall-aftersale-detail/index?id=51'])
  } finally { fixture.restore() }
})

test('return shipment remains blocked until the reviewed return address is available', async () => {
  const fixture = loadPage('pages/mall-return-shipment/index.js', {
    'services/mall-aftersale-service.js': {
      getMyMallAftersale: async () => ({ id: '51', status: 'awaiting_return', version: 3, returnInstructions: null }),
      sendMallReturn: async () => assert.fail('must not send without return instructions')
    },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' }
  })
  try {
    await fixture.page.onLoad({ id: '51' })
    assert.equal(fixture.page.data.state, 'success')
    fixture.page.onCourierChange({ detail: { value: 0 } })
    fixture.page.onTrackingInput({ detail: { value: 'SF12345678' } })
    await fixture.page.submitReturnShipment()
    assert.equal(fixture.page.data.stateMessage, '商家退货地址尚未提供，请先联系商家确认')
  } finally { fixture.restore() }
})

test('all aftersale routes are registered under the existing mall flow', () => {
  const root = path.resolve(__dirname, '../..')
  const app = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'))
  for (const route of [
    'pages/mall-aftersale-apply/index',
    'pages/mall-aftersale-detail/index',
    'pages/mall-return-shipment/index'
  ]) assert.ok(app.pages.includes(route), `missing ${route}`)
  assert.equal(app.tabBar.list.length, 5)
})

test('goods-only aftersale methods use a block-level if/else pair valid for WXML compilation', () => {
  const markup = fs.readFileSync(path.join(__dirname, '../../pages/mall-aftersale-apply/index.wxml'), 'utf8')
  assert.match(markup, /<block wx:if="\{\{scope === 'goods'\}\}">\s*<view wx:for="\{\{methods\}\}"[\s\S]*?<\/block>\s*<block wx:else>\s*<view class="mall-aftersale-option mall-aftersale-option--selected">[\s\S]*?<\/block>/)
})

test('return shipment carrier choices match the admin courier list', () => {
  const adminSource = fs.readFileSync(
    path.resolve(__dirname, '../../../manageSystem/src/pages/mall/orders/couriers.js'),
    'utf8'
  )
  const admin = [...adminSource.matchAll(/\{\s*code:\s*'([^']+)',\s*name:\s*'([^']+)'\s*\}/g)]
    .map(([, code, name]) => ({ code, name }))
  const { courierOptions } = require('../../utils/courier')
  assert.ok(admin.length >= 19)
  assert.deepEqual([...courierOptions], admin)
})

test('the required reason field is rendered and bound to the reason value', () => {
  const markup = fs.readFileSync(path.join(__dirname, '../../pages/mall-aftersale-apply/index.wxml'), 'utf8')
    .replace(/<!--[\s\S]*?-->/g, '')
  assert.match(markup, /<textarea id="mall-field-reason"[^>]*value="\{\{reason\}\}"[^>]*bindinput="onReasonInput"/)
})

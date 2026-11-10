const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function loadPage(relativePath, replacements = {}, wxOverrides = {}) {
  const root = path.resolve(__dirname, '../..')
  const pagePath = path.resolve(root, relativePath)
  const originalPage = global.Page
  const originalWx = global.wx
  const originalPages = global.getCurrentPages
  const saved = new Map()
  const dependencies = Object.assign({
    'services/mall-checkout-service.js': {
      getCheckoutSettings: async () => ({ policyVersion: 'mall-invoice-page-policy-v1' })
    }
  }, replacements)
  Object.entries(dependencies).forEach(([modulePath, exports]) => {
    const resolved = path.resolve(root, modulePath)
    saved.set(resolved, require.cache[resolved])
    require.cache[resolved] = { id: resolved, filename: resolved, loaded: true, exports }
  })
  let definition
  const navigation = []
  global.Page = (value) => { definition = value }
  global.getCurrentPages = () => [{}]
  global.wx = Object.assign({
    navigateTo(options) { navigation.push(['navigateTo', options.url]) },
    redirectTo(options) { navigation.push(['redirectTo', options.url]) },
    navigateBack(options = {}) { navigation.push(['navigateBack', options.delta || 1]) },
    showToast(options) { navigation.push(['toast', options.title]) },
    downloadFile(options) { options.fail({ errMsg: 'download failed' }) },
    openDocument(options) { options.success() }
  }, wxOverrides)
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

function paidOrder(overrides = {}) {
  return {
    id: '12', orderNo: 'M12', version: 5, status: 'completed',
    paymentStatus: 'succeeded', paidAmountCent: 12000,
    refundedGoodsCent: 2000, refundedFreightCent: 0,
    invoiceStatus: 'not_requested', invoiceRequestId: null,
    items: [], ...overrides
  }
}

test('invoice application requires a paid balance, keeps personal and company fields separate, then opens progress', async () => {
  const calls = []
  const orderService = { getMyMallOrder: async () => paidOrder() }
  const invoiceService = {
    createMallInvoiceRequest: async (application, key) => {
      calls.push({ application, key })
      return { id: '41', status: 'submitted' }
    }
  }
  const fixture = loadPage('pages/mall-invoice-apply/index.js', {
    'services/mall-order-service.js': orderService,
    'services/mall-invoice-service.js': invoiceService,
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-invoice-page-key-0001' }
  })
  try {
    await fixture.page.onLoad({ orderId: '12' })
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.netPaidText, '100.00')
    fixture.page.selectBuyerType({ currentTarget: { dataset: { type: 'company' } } })
    fixture.page.onTitleInput({ detail: { value: ' 北京鲁泰有限公司 ' } })
    fixture.page.onTaxNoInput({ detail: { value: '91110108ABCDEFGH12' } })
    fixture.page.togglePurposeConsent()
    await fixture.page.submitApplication()

    assert.deepEqual(calls, [{
      application: {
        orderId: '12', expectedOrderVersion: 5, buyerType: 'company',
        title: '北京鲁泰有限公司', taxNo: '91110108ABCDEFGH12',
        invoiceType: 'digital_normal',
        consentVersion: 'mall-invoice-page-policy-v1', consentConfirmed: true
      },
      key: 'mall-invoice-page-key-0001'
    }])
    assert.deepEqual(fixture.navigation.at(-1), ['redirectTo', '/pages/mall-invoice-detail/index?id=41'])
  } finally { fixture.restore() }
})

test('prevents an unpaid order or a company form without a tax ID from creating an invoice request', async () => {
  let createCount = 0
  const replacements = {
    'services/mall-order-service.js': { getMyMallOrder: async () => paidOrder({ paidAmountCent: 0, paymentStatus: 'not_started' }) },
    'services/mall-invoice-service.js': { createMallInvoiceRequest: async () => { createCount += 1; return { id: '41' } } },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-invoice-page-key-0002' }
  }
  const unpaid = loadPage('pages/mall-invoice-apply/index.js', replacements)
  try {
    await unpaid.page.onLoad({ orderId: '12' })
    assert.equal(unpaid.page.data.state, 'ineligible')
    assert.match(unpaid.page.data.stateMessage, /付款成功后/)
  } finally { unpaid.restore() }

  const paid = loadPage('pages/mall-invoice-apply/index.js', {
    ...replacements,
    'services/mall-order-service.js': { getMyMallOrder: async () => paidOrder() }
  })
  try {
    await paid.page.onLoad({ orderId: '12' })
    paid.page.selectBuyerType({ currentTarget: { dataset: { type: 'company' } } })
    paid.page.onTitleInput({ detail: { value: '北京鲁泰有限公司' } })
    await paid.page.submitApplication()
    assert.equal(paid.page.data.stateMessage, '企业抬头请填写纳税人识别号')
    assert.equal(paid.page.data.focusField, 'taxNo')
    assert.equal(paid.page.data.errorTarget, 'mall-field-taxNo')
    assert.equal(createCount, 0)
  } finally { paid.restore() }
})

test('retries an unknown invoice submission with the original idempotency key', async () => {
  const calls = []
  let attempts = 0
  const fixture = loadPage('pages/mall-invoice-apply/index.js', {
    'services/mall-order-service.js': { getMyMallOrder: async () => paidOrder() },
    'services/mall-invoice-service.js': {
      createMallInvoiceRequest: async (application, key) => {
        calls.push({ application, key })
        attempts += 1
        if (attempts === 1) throw Object.assign(new Error('网络暂时不可用'), { kind: 'NETWORK' })
        return { id: '41', status: 'submitted' }
      }
    },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-invoice-page-key-0003' }
  })
  try {
    await fixture.page.onLoad({ orderId: '12' })
    fixture.page.onTitleInput({ detail: { value: '王小明' } })
    await fixture.page.submitApplication()
    assert.match(fixture.page.data.stateMessage, /网络暂时不可用/)
    await fixture.page.submitApplication()
    assert.equal(calls.length, 2)
    assert.equal(calls[0].key, calls[1].key)
    assert.deepEqual(calls[0].application, calls[1].application)
    assert.equal(calls[0].application.buyerType, 'personal')
    assert.equal(Object.hasOwn(calls[0].application, 'taxNo'), false)
    assert.deepEqual(fixture.navigation.at(-1), ['redirectTo', '/pages/mall-invoice-detail/index?id=41'])
  } finally { fixture.restore() }
})

test('invoice detail shows needs-info and linked blue/red/reissue facts without exposing raw buyer data', async () => {
  const request = {
    id: '41', orderId: '12', buyerType: 'company', title: '北京鲁泰有限公司',
    invoiceType: 'manual_special_request', taxNoMasked: '91**********12', status: 'needs_info', netPaidCent: 7900, version: 4,
    invoices: [
      { id: '81', orderId: '12', requestId: '41', invoiceNo: 'BLUE-1', kind: 'blue', totalCent: 9900, status: 'fully_red', fileId: '91', version: 3 },
      { id: '82', orderId: '12', requestId: '41', invoiceNo: 'RED-1', kind: 'red', totalCent: 9900, status: 'valid', originalInvoiceId: '81', fileId: '92', version: 1 },
      { id: '83', orderId: '12', requestId: '41', invoiceNo: 'BLUE-2', kind: 'blue', totalCent: 7900, status: 'valid', replacementForId: '81', fileId: '93', version: 1 }
    ]
  }
  const fixture = loadPage('pages/mall-invoice-detail/index.js', {
    'services/mall-invoice-service.js': { getMyMallInvoiceRequest: async () => request },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' }
  })
  try {
    await fixture.page.onLoad({ id: '41' })
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.request.statusLabel, '待补充资料')
    assert.equal(fixture.page.data.request.taxNoMasked, '91**********12')
    assert.equal(fixture.page.data.request.invoiceTypeLabel, '专票需求（财务人工核实）')
    assert.equal(Object.hasOwn(fixture.page.data.request, 'taxNo'), false)
    assert.deepEqual(fixture.page.data.invoices.map((item) => item.chainLabel), ['蓝票', '原蓝票的红票', '重开蓝票'])
    assert.equal(fixture.page.data.request.canSupplement, true)
    const markup = fs.readFileSync(path.resolve(__dirname, '../../pages/mall-invoice-detail/index.wxml'), 'utf8')
    assert.match(markup, /为保护信息，税号需要重新输入/)
    assert.doesNotMatch(markup, /邮件送达即开票|邮箱送达即开票/)
  } finally { fixture.restore() }
})

test('resubmits requested missing company data using the invoice request version', async () => {
  const calls = []
  const request = {
    id: '41', orderId: '12', buyerType: 'company', title: '北京鲁泰有限公司',
    taxNoMasked: '91**********12', status: 'needs_info', netPaidCent: 10000, version: 3, invoices: []
  }
  const fixture = loadPage('pages/mall-invoice-detail/index.js', {
    'services/mall-invoice-service.js': {
      getMyMallInvoiceRequest: async () => request,
      updateMallInvoiceRequest: async (...args) => { calls.push(args); return { ...request, status: 'submitted', version: 4 } }
    },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-invoice-supplement-001' }
  })
  try {
    await fixture.page.onLoad({ id: '41' })
    fixture.page.onTitleInput({ detail: { value: '北京鲁泰有限公司' } })
    fixture.page.onTaxNoInput({ detail: { value: '91110108ABCDEFGH12' } })
    fixture.page.toggleSupplementConsent()
    await fixture.page.submitSupplement()
    assert.deepEqual(calls, [[
      '41', {
        expectedVersion: 3,
        title: '北京鲁泰有限公司',
        taxNo: '91110108ABCDEFGH12',
        consentVersion: 'mall-invoice-page-policy-v1',
        consentConfirmed: true
      },
      'mall-invoice-supplement-001'
    ]])
    assert.equal(fixture.page.data.request.statusLabel, '待财务处理')
  } finally { fixture.restore() }
})

test('allows withdrawal of an unclaimed invoice application with a reason and expected version', async () => {
  const calls = []
  const request = {
    id: '41', orderId: '12', buyerType: 'personal', title: '王小明',
    status: 'submitted', netPaidCent: 10000, version: 2, claimedBy: null, invoices: []
  }
  const fixture = loadPage('pages/mall-invoice-detail/index.js', {
    'services/mall-invoice-service.js': {
      getMyMallInvoiceRequest: async () => request,
      withdrawMallInvoiceRequest: async (...args) => {
        calls.push(args)
        return { ...request, status: 'withdrawn', version: 3 }
      }
    },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-invoice-withdraw-page-01' }
  })
  try {
    await fixture.page.onLoad({ id: '41' })
    fixture.page.startWithdraw()
    await fixture.page.submitWithdraw()
    assert.equal(calls.length, 0)
    assert.match(fixture.page.data.stateMessage, /请填写撤回原因/)
    fixture.page.onWithdrawReasonInput({ detail: { value: '暂时不需要开票' } })
    await fixture.page.submitWithdraw()
    assert.deepEqual(calls, [[
      '41', { expectedVersion: 2, reason: '暂时不需要开票' }, 'mall-invoice-withdraw-page-01'
    ]])
    assert.equal(fixture.page.data.request.statusLabel, '申请已撤回')
    assert.equal(fixture.page.data.showWithdrawForm, false)
  } finally { fixture.restore() }
})

test('fresh-link retry downloads a private PDF and opens it only after the second attempt succeeds', async () => {
  let downloadAttempts = 0
  const accessCalls = []
  const opened = []
  const invoice = { id: '83', kind: 'blue', invoiceNo: 'BLUE-2', totalCent: 7900, status: 'valid', fileId: '93', version: 1 }
  const fixture = loadPage('pages/mall-invoice-detail/index.js', {
    'services/mall-invoice-service.js': {
      getMyMallInvoiceRequest: async () => ({ id: '41', orderId: '12', status: 'delivered', version: 2, invoices: [invoice] }),
      getMallInvoiceFileAccess: async (fileId) => {
        accessCalls.push(fileId)
        return { accessUrl: `https://private.example/${accessCalls.length}.pdf?temporary=${accessCalls.length}` }
      }
    },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' }
  }, {
    downloadFile(options) {
      downloadAttempts += 1
      if (downloadAttempts === 1) options.fail({ errMsg: 'expired' })
      else options.success({ statusCode: 200, tempFilePath: '/tmp/invoice.pdf' })
    },
    openDocument(options) { opened.push(options); options.success() }
  })
  try {
    await fixture.page.onLoad({ id: '41' })
    const event = { currentTarget: { dataset: { fileId: '93', invoiceId: '83' } } }
    await fixture.page.downloadInvoice(event)
    assert.match(fixture.page.data.downloadMessage, /下载失败/)
    await fixture.page.downloadInvoice(event)
    assert.deepEqual(accessCalls, ['93', '93'])
    assert.equal(opened.length, 1)
    assert.equal(opened[0].filePath, '/tmp/invoice.pdf')
    assert.equal(opened[0].fileType, 'pdf')
    assert.equal(opened[0].showMenu, true)
    assert.equal(fixture.page.data.downloadMessage, '')
  } finally { fixture.restore() }
})

test('a correction request stays a manual review, separate from invoice issuance', async () => {
  const calls = []
  const invoice = { id: '83', kind: 'blue', invoiceNo: 'BLUE-2', totalCent: 7900, status: 'valid', fileId: '93', version: 2 }
  const fixture = loadPage('pages/mall-invoice-detail/index.js', {
    'services/mall-invoice-service.js': {
      getMyMallInvoiceRequest: async () => ({ id: '41', orderId: '12', status: 'delivered', version: 2, invoices: [invoice] }),
      requestMallInvoiceCorrection: async (...args) => { calls.push(args); return { commandId: '104', status: 'manual', version: 1 } }
    },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-invoice-correction-001' }
  })
  try {
    await fixture.page.onLoad({ id: '41' })
    fixture.page.startCorrection({ currentTarget: { dataset: { invoiceId: '83' } } })
    fixture.page.onCorrectionReasonInput({ detail: { value: '购方名称需要更正' } })
    await fixture.page.submitCorrection()
    assert.deepEqual(calls, [['83', { expectedVersion: 2, reason: '购方名称需要更正' }, 'mall-invoice-correction-001']])
    assert.match(fixture.page.data.correctionMessage, /已提交更正诉求/)
    assert.equal(fixture.page.data.request.status, 'delivered')
    assert.equal(fixture.page.data.invoices[0].status, 'valid')
  } finally { fixture.restore() }
})

test('order detail links paid unbilled orders to apply and existing invoice requests to progress', async () => {
  const fixture = loadPage('pages/mall-order-detail/index.js', {
    'services/mall-order-service.js': { getMyMallOrder: async () => paidOrder() },
    'services/mall-intent-service.js': { createIdempotencyKey: () => 'mall-receipt-page-key-0001' },
    'services/session-service.js': { getAccessToken: () => 'buyer-token' }
  })
  try {
    await fixture.page.onLoad({ id: '12' })
    fixture.page.openInvoice()
    assert.deepEqual(fixture.navigation.at(-1), ['navigateTo', '/pages/mall-invoice-apply/index?orderId=12'])

    fixture.page.setData({ order: { ...fixture.page.data.order, invoiceRequestId: '41' } })
    fixture.page.openInvoice()
    assert.deepEqual(fixture.navigation.at(-1), ['navigateTo', '/pages/mall-invoice-detail/index?id=41'])
    const root = path.resolve(__dirname, '../..')
    const app = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'))
    assert.ok(app.pages.includes('pages/mall-invoice-apply/index'))
    assert.ok(app.pages.includes('pages/mall-invoice-detail/index'))
    assert.equal(app.tabBar.list.length, 5)
    const markup = fs.readFileSync(path.join(root, 'pages/mall-order-detail/index.wxml'), 'utf8')
    assert.match(markup, /bindtap="openInvoice"/)
  } finally { fixture.restore() }
})

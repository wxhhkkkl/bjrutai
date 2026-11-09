const test = require('node:test')
const assert = require('node:assert/strict')

const { createMallInvoiceService } = require('../../services/mall-invoice-service')

function fixture(options = {}) {
  const calls = []
  let accessCount = 0
  const service = createMallInvoiceService({
    getAccessToken: options.getAccessToken || (() => 'buyer-token'),
    request: async (path, requestOptions = {}) => {
      calls.push({ path, options: requestOptions })
      if (path.endsWith('/access')) {
        accessCount += 1
        return {
          fileId: '82',
          accessUrl: `https://private.example/invoice-${accessCount}.pdf?signature=short-lived`,
          expiresAt: '2026-11-07T10:01:00Z'
        }
      }
      if (path.endsWith('/correction')) return { commandId: '91', status: 'manual', version: 1 }
      return options.response || { id: '41', orderId: '12', status: 'submitted', version: 1, invoices: [] }
    }
  })
  return { service, calls }
}

const personalApplication = {
  orderId: '12',
  expectedOrderVersion: 5,
  buyerType: 'personal',
  title: '王小明',
  email: 'buyer@example.com',
  invoiceType: 'digital_normal'
}

const companyApplication = {
  orderId: '12',
  expectedOrderVersion: 5,
  buyerType: 'company',
  title: '北京鲁泰有限公司',
  taxNo: '91110108ABCDEFGH12',
  invoiceType: 'digital_normal'
}

test('requires a buyer session before reading or changing private invoice facts', async () => {
  const f = fixture({ getAccessToken: () => '' })

  assert.throws(() => f.service.listMyMallInvoices('12'), { kind: 'AUTH' })
  assert.throws(() => f.service.getMyMallInvoiceRequest('41'), { kind: 'AUTH' })
  assert.throws(() => f.service.getMallInvoiceFileAccess('82'), { kind: 'AUTH' })
  assert.throws(() => f.service.requestMallInvoiceCorrection('83', { expectedVersion: 1, reason: '抬头错误' }, 'mall-invoice-correct-01'), { kind: 'AUTH' })
  assert.equal(f.calls.length, 0)
})

test('creates personal and company invoice applications using buyer contracts and stable retry keys', async () => {
  const f = fixture()
  await f.service.createMallInvoiceRequest(personalApplication, 'mall-invoice-create-001')
  await f.service.createMallInvoiceRequest(companyApplication, 'mall-invoice-create-002')
  await f.service.createMallInvoiceRequest(companyApplication, 'mall-invoice-create-002')

  assert.deepEqual(f.calls, [
    {
      path: '/api/v1/mall/invoice-requests',
      options: {
        method: 'POST',
        data: personalApplication,
        idempotencyKey: 'mall-invoice-create-001'
      }
    },
    {
      path: '/api/v1/mall/invoice-requests',
      options: {
        method: 'POST',
        data: companyApplication,
        idempotencyKey: 'mall-invoice-create-002'
      }
    },
    {
      path: '/api/v1/mall/invoice-requests',
      options: {
        method: 'POST',
        data: companyApplication,
        idempotencyKey: 'mall-invoice-create-002'
      }
    }
  ])
})

test('lists an owned order invoice chain and reads the application status without exposing raw tax IDs', async () => {
  const invoice = {
    id: '82', orderId: '12', requestId: '41', invoiceNo: 'E-1002',
    kind: 'red', totalCent: 19900, status: 'issued', originalInvoiceId: '80',
    replacementForId: null, fileId: '92', sellerIdentity: '北京鲁泰有限公司'
  }
  const request = {
    id: '41', orderId: '12', buyerType: 'company', title: '北京鲁泰有限公司',
    taxNoMasked: '91**********12', status: 'needs_info', netPaidCent: 19900,
    invoices: [invoice], version: 3
  }
  const f = fixture({ response: request })

  const page = await f.service.listMyMallInvoices('12', { pageSize: 10, cursor: 'opaque+/=' })
  const detail = await f.service.getMyMallInvoiceRequest('41')

  assert.deepEqual(f.calls, [
    {
      path: '/api/v1/mall/orders/12/invoices',
      options: { data: { pageSize: 10, cursor: 'opaque+/=' } }
    },
    { path: '/api/v1/mall/invoice-requests/41', options: {} }
  ])
  assert.deepEqual(page.invoices, [invoice])
  assert.equal(detail.status, 'needs_info')
  assert.equal(detail.taxNoMasked, '91**********12')
  assert.equal(Object.hasOwn(detail, 'taxNo'), false)
  assert.equal(detail.invoices[0].originalInvoiceId, '80')
})

test('updates or withdraws an editable application and sends correction as a separate request', async () => {
  const f = fixture()
  await f.service.updateMallInvoiceRequest('41', {
    expectedVersion: 2,
    title: '北京鲁泰健康科技有限公司',
    taxNo: '91110108ABCDEFGH34',
    email: null
  }, 'mall-invoice-edit-0001')
  await f.service.withdrawMallInvoiceRequest('41', {
    expectedVersion: 3,
    reason: '暂时不需要发票'
  }, 'mall-invoice-withdraw-1')
  const correction = await f.service.requestMallInvoiceCorrection('82', {
    expectedVersion: 1,
    reason: '购方名称需要更正'
  }, 'mall-invoice-correct-01')

  assert.deepEqual(f.calls, [
    {
      path: '/api/v1/mall/invoice-requests/41',
      options: {
        method: 'PATCH',
        data: { expectedVersion: 2, title: '北京鲁泰健康科技有限公司', taxNo: '91110108ABCDEFGH34', email: null },
        idempotencyKey: 'mall-invoice-edit-0001'
      }
    },
    {
      path: '/api/v1/mall/invoice-requests/41/withdraw',
      options: {
        method: 'POST', data: { expectedVersion: 3, reason: '暂时不需要发票' },
        idempotencyKey: 'mall-invoice-withdraw-1'
      }
    },
    {
      path: '/api/v1/mall/invoices/82/correction',
      options: {
        method: 'POST', data: { expectedVersion: 1, reason: '购方名称需要更正' },
        idempotencyKey: 'mall-invoice-correct-01'
      }
    }
  ])
  assert.deepEqual(correction, { commandId: '91', status: 'manual', version: 1 })
  assert.equal(correction.status, 'manual', 'a correction request is not represented as an issued tax invoice')
})

test('requests a fresh private invoice link on each download attempt', async () => {
  const f = fixture()

  const first = await f.service.getMallInvoiceFileAccess('82')
  const retry = await f.service.getMallInvoiceFileAccess('82')

  assert.deepEqual(f.calls, [
    { path: '/api/v1/mall/files/82/access', options: {} },
    { path: '/api/v1/mall/files/82/access', options: {} }
  ])
  assert.notEqual(first.accessUrl, retry.accessUrl)
  assert.equal(first.expiresAt, '2026-11-07T10:01:00Z')
})

test('validates invoice forms, identifiers, pagination, versions and idempotency keys before transport', async () => {
  const f = fixture()

  assert.throws(() => f.service.listMyMallInvoices('../12'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.listMyMallInvoices('12', { pageSize: 101 }), { kind: 'VALIDATION' })
  assert.throws(() => f.service.getMyMallInvoiceRequest('0'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.createMallInvoiceRequest({ ...personalApplication, expectedOrderVersion: 0 }, 'mall-invoice-create-003'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.createMallInvoiceRequest({ ...companyApplication, taxNo: '' }, 'mall-invoice-create-004'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.createMallInvoiceRequest({ ...personalApplication, taxNo: '91110108ABCDEFGH12' }, 'mall-invoice-create-005'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.createMallInvoiceRequest({ ...personalApplication, email: 'not-an-email' }, 'mall-invoice-create-006'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.createMallInvoiceRequest(personalApplication, 'short'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.updateMallInvoiceRequest('41', { expectedVersion: 1 }, 'mall-invoice-edit-0002'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.withdrawMallInvoiceRequest('41', { expectedVersion: 1, reason: ' ' }, 'mall-invoice-withdraw-2'), { kind: 'VALIDATION' })
  assert.throws(() => f.service.getMallInvoiceFileAccess('82/../other'), { kind: 'VALIDATION' })

  assert.equal(f.calls.length, 0)
})

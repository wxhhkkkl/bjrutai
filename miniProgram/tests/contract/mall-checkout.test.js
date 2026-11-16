const test = require('node:test')
const assert = require('node:assert/strict')

const { createMallCheckoutService } = require('../../services/mall-checkout-service')

test('checkout service uses safe settings, authenticated address/cart routes and server quotes', async () => {
  const calls = []
  const service = createMallCheckoutService({
    getAccessToken: () => 'buyer-token',
    request: async (path, options = {}) => {
      calls.push({ path, options })
      return { items: [], total: 0 }
    }
  })

  await service.getCheckoutSettings()
  await service.listAddresses({ pageSize: 10 })
  await service.getCart()
  await service.quoteOrder({
    addressId: '8',
    items: [{ skuId: '10', quantity: 2 }]
  })

  assert.deepEqual(calls.map(({ path }) => path), [
    '/api/v1/mall/checkout/settings',
    '/api/v1/mall/addresses',
    '/api/v1/mall/cart',
    '/api/v1/mall/checkout/quote'
  ])
  assert.equal(calls[0].options.auth, false)
  assert.deepEqual(calls[1].options.data, { pageSize: 10 })
  assert.deepEqual(calls[3].options.data, {
    addressId: '8',
    items: [{ skuId: '10', quantity: 2 }]
  })
})

test('address save requires a current-policy confirmation and sends only API fields', async () => {
  const calls = []
  const service = createMallCheckoutService({
    getAccessToken: () => 'buyer-token',
    request: async (path, options) => { calls.push({ path, options }); return {} }
  })
  const address = {
    recipientName: '买家',
    phone: '13800138000',
    regionCodes: ['110000', '110100', '110101'],
    addressLine: '朝阳路1号',
    isDefault: true,
    consentVersion: 'policy-v3',
    consentConfirmed: true
  }

  await service.createAddress(address, 'mall-address-key-0001')

  assert.equal(calls[0].path, '/api/v1/mall/addresses')
  assert.equal(calls[0].options.idempotencyKey, 'mall-address-key-0001')
  assert.deepEqual(calls[0].options.data, {
    recipientName: '买家',
    phone: '13800138000',
    regionCodes: ['110000', '110100', '110101'],
    addressLine: '朝阳路1号',
    isDefault: true,
    consentVersion: 'policy-v3',
    consentConfirmed: true
  })
  assert.throws(
    () => service.createAddress({ ...address, consentConfirmed: false }, 'mall-address-key-0002'),
    /仅用于商城订单履约/
  )
  assert.throws(
    () => service.createAddress({ ...address, regionCodes: ['110000', 'bad', '110101'] }, 'mall-address-key-0003'),
    /地区编码/
  )
})

test('order create retries preserve the caller-owned idempotency key and invoice intent', async () => {
  const calls = []
  const service = createMallCheckoutService({
    getAccessToken: () => 'buyer-token',
    request: async (path, options) => {
      calls.push({ path, options })
      return { id: '31' }
    }
  })
  const input = {
    quoteToken: 'signed-short-lived-quote',
    consentVersion: 'policy-v3',
    invoiceIntent: true
  }
  await service.createOrder(input, 'mall-order-key-0001')
  await service.createOrder(input, 'mall-order-key-0001')

  assert.equal(calls.length, 2)
  assert.ok(calls.every((call) => call.path === '/api/v1/mall/orders'))
  assert.ok(calls.every((call) => call.options.idempotencyKey === 'mall-order-key-0001'))
  assert.ok(calls.every((call) => call.options.data.invoiceIntent === true))
})

test('private checkout reads and writes fail closed when buyer authentication is missing', async () => {
  const service = createMallCheckoutService({
    getAccessToken: () => '',
    request: async () => ({})
  })

  assert.throws(() => service.listAddresses(), { kind: 'AUTH' })
  assert.throws(() => service.getCart(), { kind: 'AUTH' })
  assert.throws(() => service.createOrder({ quoteToken: 'x', consentVersion: 'v1' }, 'mall-order-key-0001'), { kind: 'AUTH' })
})

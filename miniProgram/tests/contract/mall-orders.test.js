const test = require('node:test')
const assert = require('node:assert/strict')

const { createMallOrderService } = require('../../services/mall-order-service')

test('lists buyer orders with supported filters and cursor pagination', async () => {
  const calls = []
  const service = createMallOrderService({
    getAccessToken: () => 'buyer-token',
    request: async (path, options = {}) => {
      calls.push({ path, options })
      return { items: [], nextCursor: null, total: 0 }
    }
  })

  await service.listMyMallOrders({ status: 'pending_receipt', pageSize: 12, cursor: 'opaque-next' })

  assert.deepEqual(calls, [{
    path: '/api/v1/mall/orders',
    options: { data: { status: 'pending_receipt', pageSize: 12, cursor: 'opaque-next' } }
  }])
})

test('rejects unsupported order filters, invalid page sizes and oversized cursors before transport', async () => {
  let calls = 0
  const service = createMallOrderService({
    getAccessToken: () => 'buyer-token',
    request: async () => { calls += 1; return {} }
  })

  assert.throws(() => service.listMyMallOrders({ status: 'processing' }), { kind: 'VALIDATION' })
  assert.throws(() => service.listMyMallOrders({ pageSize: 1.5 }), { kind: 'VALIDATION' })
  assert.throws(() => service.listMyMallOrders({ cursor: 'x'.repeat(2049) }), { kind: 'VALIDATION' })
  assert.equal(calls, 0)
})

test('reads only the current buyer order and logistics paths with validated identities', async () => {
  const calls = []
  const service = createMallOrderService({
    getAccessToken: () => 'buyer-token',
    request: async (path, options = {}) => {
      calls.push({ path, options })
      return path.endsWith('/logistics')
        ? { source: null, queryStatus: 'config_required', events: [], mapAvailable: false }
        : { id: '42', status: 'pending_receipt' }
    }
  })

  const order = await service.getMyMallOrder('42')
  const logistics = await service.getMyMallLogistics('42')

  assert.equal(order.id, '42')
  assert.equal(logistics.source, null)
  assert.equal(logistics.queryStatus, 'config_required')
  assert.deepEqual(calls.map((call) => call.path), [
    '/api/v1/mall/orders/42',
    '/api/v1/mall/orders/42/logistics'
  ])
  assert.throws(() => service.getMyMallOrder('../42'), { kind: 'VALIDATION' })
  assert.throws(() => service.getMyMallLogistics('0'), { kind: 'VALIDATION' })
})

test('keeps provider and platform states factual instead of inventing shipment progress', async () => {
  const snapshot = {
    provider: 'kuaidi100',
    source: null,
    queryStatus: 'config_required',
    stateCode: null,
    stateName: null,
    events: [],
    mapAvailable: false
  }
  const service = createMallOrderService({
    getAccessToken: () => 'buyer-token',
    request: async () => snapshot
  })

  assert.deepEqual(await service.getMyMallLogistics('9'), snapshot)
})

test('confirms receipt with the server order version and a reusable idempotency key', async () => {
  const calls = []
  const service = createMallOrderService({
    getAccessToken: () => 'buyer-token',
    request: async (path, options = {}) => { calls.push({ path, options }); return { status: 'completed' } }
  })

  const input = ['52', 7, 'mall-receipt-key-0001']
  await service.confirmMallReceipt(...input)
  await service.confirmMallReceipt(...input)

  assert.equal(calls.length, 2)
  assert.ok(calls.every((call) => call.path === '/api/v1/mall/orders/52/confirm-receipt'))
  assert.ok(calls.every((call) => call.options.method === 'POST'))
  assert.ok(calls.every((call) => call.options.idempotencyKey === input[2]))
  assert.ok(calls.every((call) => call.options.data.expectedVersion === 7))
  assert.throws(() => service.confirmMallReceipt('52', 0, input[2]), { kind: 'VALIDATION' })
  assert.throws(() => service.confirmMallReceipt('52', 7, 'short'), { kind: 'VALIDATION' })
})

test('all private order and logistics actions fail closed without a buyer session', async () => {
  const service = createMallOrderService({ getAccessToken: () => '', request: async () => ({}) })

  assert.throws(() => service.listMyMallOrders(), { kind: 'AUTH' })
  assert.throws(() => service.getMyMallOrder('1'), { kind: 'AUTH' })
  assert.throws(() => service.getMyMallLogistics('1'), { kind: 'AUTH' })
  assert.throws(() => service.confirmMallReceipt('1', 1, 'mall-receipt-key-0001'), { kind: 'AUTH' })
})

const test = require('node:test')
const assert = require('node:assert/strict')

const {
  classifyPaymentState,
  createMallPaymentService
} = require('../../services/mall-payment-service')

test('payment state requires server verification; a client callback cannot mark an order paid', () => {
  assert.equal(classifyPaymentState({ status: 'pending_payment', paymentStatus: 'not_started' }, null), 'not_started')
  assert.equal(classifyPaymentState({ status: 'pending_payment', paymentStatus: 'pending' }, null), 'pending')
  assert.equal(classifyPaymentState({ status: 'pending_payment', paymentStatus: 'unknown' }, null), 'unknown')
  assert.equal(classifyPaymentState({ status: 'pending_payment', paymentStatus: 'succeeded' }, null), 'succeeded')
  assert.equal(classifyPaymentState({ status: 'closed', paymentStatus: 'closed' }, null), 'closed')
})

test('payment success callback still queries the original payment and order before reporting', async () => {
  const calls = []
  const service = createMallPaymentService({
    getAccessToken: () => 'buyer-token',
    requestPayment: async () => ({ errMsg: 'requestPayment:ok' }),
    request: async (path, options = {}) => {
      calls.push({ path, options })
      if (options.method === 'POST') {
        return { canInvoke: true, invokeParams: { timeStamp: '1', nonceStr: 'n' } }
      }
      if (path.endsWith('/payment')) return { status: 'pending', amountCent: 1200 }
      return { id: '31', status: 'pending_payment', paymentStatus: 'pending', paidAmountCent: 0 }
    }
  })

  const result = await service.payOrder('31', 1, 'mall-payment-key-0001')

  assert.equal(result.status, 'pending')
  assert.equal(calls.some((call) => call.path === '/api/v1/mall/orders/31/payment' && !call.options.method), true)
  assert.equal(calls.some((call) => call.path === '/api/v1/mall/orders/31' && !call.options.method), true)
  assert.ok(calls.every((call) => !JSON.stringify(call.options).includes('timeStamp')))
})

test('client payment cancellation never closes the order and recovers status by querying the original ID', async () => {
  const calls = []
  const service = createMallPaymentService({
    getAccessToken: () => 'buyer-token',
    requestPayment: async () => { throw new Error('requestPayment:fail cancel') },
    request: async (path, options = {}) => {
      calls.push({ path, options })
      if (options.method === 'POST') return { canInvoke: true, invokeParams: { nonceStr: 'n' } }
      if (path.endsWith('/payment')) return { status: 'pending', amountCent: 1200 }
      return { id: '31', status: 'pending_payment', paymentStatus: 'pending', paidAmountCent: 0 }
    }
  })

  const result = await service.payOrder('31', 1, 'mall-payment-key-0002')

  assert.equal(result.status, 'pending')
  assert.equal(result.requestPaymentOutcome, 'cancelled')
  assert.ok(calls.every((call) => !call.path.endsWith('/cancel')))
})

test('unknown query results stay unknown and a disabled invocation never calls WeChat payment', async () => {
  let invocationCount = 0
  const service = createMallPaymentService({
    getAccessToken: () => 'buyer-token',
    requestPayment: async () => { invocationCount += 1 },
    request: async (path, options = {}) => {
      if (options.method === 'POST') return { canInvoke: false, invokeParams: null }
      throw new Error('network timeout')
    }
  })

  const result = await service.payOrder('31', 1, 'mall-payment-key-0003')

  assert.equal(result.status, 'unknown')
  assert.equal(invocationCount, 0)
})

test('prepay preparation is awaited so one payment tap opens the sheet without a status re-check', async () => {
  let posts = 0
  let invocationCount = 0
  const service = createMallPaymentService({
    getAccessToken: () => 'buyer-token',
    sleep: async () => {},
    requestPayment: async (params) => {
      invocationCount += 1
      assert.equal(params.timeStamp, '2')
    },
    request: async (path, options = {}) => {
      if (options.method === 'POST') {
        posts += 1
        return posts === 1
          ? { canInvoke: false, invokeParams: null }
          : { canInvoke: true, invokeParams: { timeStamp: '2', nonceStr: 'n' } }
      }
      if (path.endsWith('/payment')) return { status: 'pending', amountCent: 1200 }
      return { id: '31', status: 'pending_payment', paymentStatus: 'pending', paidAmountCent: 0 }
    }
  })

  const result = await service.payOrder('31', 1, 'mall-payment-key-0004')

  assert.equal(posts, 2)
  assert.equal(invocationCount, 1)
  assert.equal(result.requestPaymentOutcome, 'submitted')
  assert.equal(result.status, 'pending')
})

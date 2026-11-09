const test = require('node:test')
const assert = require('node:assert/strict')

const { createMallIntentService } = require('../../services/mall-intent-service')

function memoryStorage() {
  const values = new Map()
  return {
    values,
    get(key) { return values.get(key) || null },
    set(key, value) { values.set(key, value) },
    remove(key) { values.delete(key) }
  }
}

test('guest buy intent survives login without storing buyer address or phone', () => {
  const storage = memoryStorage()
  let userId = ''
  const service = createMallIntentService({ storage, getUserId: () => userId, now: () => 1000 })

  service.savePendingIntent({ action: 'buy_now', skuId: '7', quantity: 2 })
  userId = 'buyer-42'
  const resumed = service.getPendingIntent()

  assert.deepEqual(resumed, {
    action: 'buy_now',
    skuId: '7',
    quantity: 2,
    idempotencyKey: resumed.idempotencyKey,
    userId: 'buyer-42',
    createdAt: 1000
  })
  assert.equal(storage.values.has('mall_pending_intent'), true)
  assert.doesNotMatch(JSON.stringify(storage.values.get('mall_pending_intent')), /phone|addressLine|recipientName/)
})

test('checkout drafts persist only SKU and address identities, not copied private address data', () => {
  const storage = memoryStorage()
  const service = createMallIntentService({ storage, getUserId: () => 'buyer-42', now: () => 5000 })

  service.saveCheckoutDraft({
    items: [{ skuId: '7', quantity: 2 }],
    addressId: '8',
    recipientName: '不应保存',
    phone: '13800138000',
    addressLine: '不应保存'
  })

  assert.deepEqual(service.getCheckoutDraft(), {
    items: [{ skuId: '7', quantity: 2 }],
    addressId: '8',
    source: 'cart',
    userId: 'buyer-42',
    createdAt: 5000
  })
  assert.doesNotMatch(JSON.stringify(storage.values.get('mall_checkout_draft')), /13800138000|不应保存/)
})

test('ambiguous order submission keeps the exact quote and idempotency key for replay', () => {
  const storage = memoryStorage()
  const service = createMallIntentService({ storage, getUserId: () => 'buyer-42', now: () => 9000 })
  const submission = {
    quoteToken: 'opaque-server-signed-token',
    consentVersion: 'policy-v3',
    invoiceIntent: true,
    buyerNote: '请放门口',
    idempotencyKey: 'mall-order-idempotency-0001'
  }

  service.saveOrderSubmission(submission)
  assert.deepEqual(service.getOrderSubmission(), { ...submission, userId: 'buyer-42', createdAt: 9000 })
  service.clearOrderSubmission()
  assert.equal(service.getOrderSubmission(), null)
})

test('expired or different-account intents are cleared instead of resumed', () => {
  const storage = memoryStorage()
  let now = 1000
  let userId = 'buyer-a'
  const service = createMallIntentService({ storage, getUserId: () => userId, now: () => now })
  service.savePendingIntent({ action: 'add_to_cart', skuId: '7', quantity: 1 })
  userId = 'buyer-b'
  assert.equal(service.getPendingIntent(), null)
  assert.equal(storage.get('mall_pending_intent'), null)

  userId = 'buyer-a'
  service.savePendingIntent({ action: 'buy_now', skuId: '7', quantity: 1 })
  now += 31 * 60 * 1000
  assert.equal(service.getPendingIntent(), null)
})

test('payment recovery routes back to the original order after login', () => {
  const storage = memoryStorage()
  const service = createMallIntentService({ storage, getUserId: () => 'buyer-42', now: () => 12000 })
  service.savePendingOrder('31')

  assert.equal(service.getPendingOrder().orderId, '31')
  assert.equal(service.resumePath(), '/pages/mall-payment-result/index?id=31')
  service.clearPendingOrder()
  assert.equal(service.getPendingOrder(), null)
})

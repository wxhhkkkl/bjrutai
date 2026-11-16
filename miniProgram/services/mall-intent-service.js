const { getCurrentSession } = require('./session-service')

const PENDING_KEY = 'mall_pending_intent'
const DRAFT_KEY = 'mall_checkout_draft'
const ORDER_KEY = 'mall_order_submission'
const PENDING_ORDER_KEY = 'mall_pending_order'
const PENDING_TTL_MS = 30 * 60 * 1000
const DRAFT_TTL_MS = 30 * 60 * 1000
const ORDER_TTL_MS = 7 * 24 * 60 * 60 * 1000

function validId(value) {
  const id = String(value === undefined || value === null ? '' : value)
  return /^[1-9][0-9]*$/.test(id) ? id : ''
}

function newIdempotencyKey() {
  const random = Math.random().toString(36).slice(2)
  return `mall_${Date.now().toString(36)}_${random}`
}

function paymentIdempotencyKey(orderId, expectedVersion) {
  const id = validId(orderId)
  if (!id || !Number.isInteger(expectedVersion) || expectedVersion < 1) throw new Error('支付请求版本不合法')
  return `mall_payment_${id}_${expectedVersion}`
}

function defaultStorage() {
  return {
    get(key) {
      try { return typeof wx !== 'undefined' && wx.getStorageSync ? wx.getStorageSync(key) : null } catch (_) { return null }
    },
    set(key, value) {
      if (typeof wx !== 'undefined' && wx.setStorageSync) wx.setStorageSync(key, value)
    },
    remove(key) {
      if (typeof wx !== 'undefined' && wx.removeStorageSync) wx.removeStorageSync(key)
    }
  }
}

function createMallIntentService(options = {}) {
  const storage = options.storage || defaultStorage()
  const now = options.now || Date.now
  const keyFactory = options.keyFactory || newIdempotencyKey
  const getUserId = options.getUserId || (() => {
    const session = getCurrentSession()
    return String((session && session.userId) || '')
  })

  function readOwned(key, ttl) {
    const value = storage.get(key)
    if (!value || typeof value !== 'object' || !Number.isFinite(value.createdAt)) return null
    if (now() - value.createdAt > ttl || value.createdAt > now() + 60 * 1000) {
      storage.remove(key)
      return null
    }
    const currentUserId = String(getUserId() || '')
    const savedUserId = String(value.userId || '')
    if (savedUserId && savedUserId !== currentUserId) {
      storage.remove(key)
      return null
    }
    if (!savedUserId && currentUserId) {
      const claimed = { ...value, userId: currentUserId }
      storage.set(key, claimed)
      return claimed
    }
    return value
  }

  function savePendingIntent(intent = {}) {
    const action = intent.action
    const skuId = validId(intent.skuId)
    const quantity = intent.quantity
    if (!['add_to_cart', 'buy_now'].includes(action) || !skuId || !Number.isInteger(quantity) || quantity < 1 || quantity > 999) {
      throw new Error('待继续的商品操作不合法')
    }
    const idempotencyKey = typeof intent.idempotencyKey === 'string' ? intent.idempotencyKey : keyFactory()
    if (idempotencyKey.length < 16 || idempotencyKey.length > 128) throw new Error('商品操作凭证不合法')
    const value = {
      action,
      skuId,
      quantity,
      idempotencyKey,
      deliveryMethod: intent.deliveryMethod === 'virtual' ? 'virtual' : 'express',
      userId: String(getUserId() || ''),
      createdAt: now()
    }
    storage.set(PENDING_KEY, value)
    return value
  }

  function getPendingIntent() {
    const saved = readOwned(PENDING_KEY, PENDING_TTL_MS)
    if (!saved) return null
    const skuId = validId(saved.skuId)
    if (!skuId || !['add_to_cart', 'buy_now'].includes(saved.action) || !Number.isInteger(saved.quantity)) {
      storage.remove(PENDING_KEY)
      return null
    }
    return {
      action: saved.action,
      skuId,
      quantity: saved.quantity,
      idempotencyKey: String(saved.idempotencyKey || ''),
      deliveryMethod: saved.deliveryMethod === 'virtual' ? 'virtual' : 'express',
      userId: String(saved.userId || ''),
      createdAt: saved.createdAt
    }
  }

  function clearPendingIntent() {
    storage.remove(PENDING_KEY)
  }

  function normalizeDraft(value = {}) {
    const items = Array.isArray(value.items) ? value.items.map((item) => {
      const skuId = validId(item && item.skuId)
      const quantity = item && item.quantity
      if (!skuId || !Number.isInteger(quantity) || quantity < 1 || quantity > 999) {
        throw new Error('结算商品资料不合法')
      }
      return { skuId, quantity }
    }) : []
    if (!items.length || items.length > 50 || new Set(items.map((item) => item.skuId)).size !== items.length) {
      throw new Error('结算商品数量不合法')
    }
    const addressId = value.addressId ? validId(value.addressId) : ''
    if (value.addressId && !addressId) throw new Error('收货地址编号不合法')
    return {
      items,
      addressId,
      deliveryMethod: value.deliveryMethod === 'virtual' ? 'virtual' : 'express',
      source: value.source === 'buy_now' ? 'buy_now' : 'cart',
      userId: String(getUserId() || ''),
      createdAt: now()
    }
  }

  function saveCheckoutDraft(value) {
    const draft = normalizeDraft(value)
    storage.set(DRAFT_KEY, draft)
    return draft
  }

  function getCheckoutDraft() {
    const saved = readOwned(DRAFT_KEY, DRAFT_TTL_MS)
    if (!saved) return null
    try {
      const normalized = normalizeDraft({
        items: saved.items,
        addressId: saved.addressId,
        deliveryMethod: saved.deliveryMethod,
        source: saved.source
      })
      return { ...normalized, userId: String(saved.userId || ''), createdAt: saved.createdAt }
    } catch (_) {
      storage.remove(DRAFT_KEY)
      return null
    }
  }

  function clearCheckoutDraft() {
    storage.remove(DRAFT_KEY)
  }

  function saveOrderSubmission(value = {}) {
    const quoteToken = typeof value.quoteToken === 'string' ? value.quoteToken : ''
    const consentVersion = typeof value.consentVersion === 'string' ? value.consentVersion : ''
    const idempotencyKey = typeof value.idempotencyKey === 'string' ? value.idempotencyKey : ''
    if (!quoteToken || quoteToken.length > 32768 || !consentVersion || consentVersion.length > 128 || idempotencyKey.length < 16 || idempotencyKey.length > 128) {
      throw new Error('订单提交凭证不完整')
    }
    const buyerNote = typeof value.buyerNote === 'string' ? value.buyerNote.trim() : ''
    if (buyerNote.length > 200) throw new Error('订单备注不能超过200个字符')
    const saved = {
      quoteToken,
      consentVersion,
      consentConfirmed: value.consentConfirmed === true,
      buyerNote,
      invoiceIntent: value.invoiceIntent === true,
      idempotencyKey,
      userId: String(getUserId() || ''),
      createdAt: now()
    }
    storage.set(ORDER_KEY, saved)
    return saved
  }

  function getOrderSubmission() {
    const saved = readOwned(ORDER_KEY, ORDER_TTL_MS)
    if (!saved) return null
    return {
      quoteToken: saved.quoteToken,
      consentVersion: saved.consentVersion,
      consentConfirmed: saved.consentConfirmed === true,
      buyerNote: saved.buyerNote || '',
      invoiceIntent: saved.invoiceIntent === true,
      idempotencyKey: String(saved.idempotencyKey || ''),
      userId: String(saved.userId || ''),
      createdAt: saved.createdAt
    }
  }

  function clearOrderSubmission() {
    storage.remove(ORDER_KEY)
  }

  function savePendingOrder(orderId) {
    const id = validId(orderId)
    if (!id) throw new Error('订单编号不合法')
    const value = { orderId: id, userId: String(getUserId() || ''), createdAt: now() }
    storage.set(PENDING_ORDER_KEY, value)
    return value
  }

  function getPendingOrder() {
    const saved = readOwned(PENDING_ORDER_KEY, ORDER_TTL_MS)
    if (!saved) return null
    const orderId = validId(saved.orderId)
    if (!orderId) {
      storage.remove(PENDING_ORDER_KEY)
      return null
    }
    return { orderId, userId: String(saved.userId || ''), createdAt: saved.createdAt }
  }

  function clearPendingOrder() {
    storage.remove(PENDING_ORDER_KEY)
  }

  function resumePath() {
    const pendingOrder = getPendingOrder()
    if (pendingOrder) return `/pages/mall-payment-result/index?id=${encodeURIComponent(pendingOrder.orderId)}`
    const pending = getPendingIntent()
    if (pending) return pending.action === 'buy_now'
      ? '/pages/mall-checkout/index?resume=1'
      : '/pages/mall-cart/index?resume=1'
    return getCheckoutDraft() ? '/pages/mall-checkout/index?resume=1' : '/pages/mall-cart/index?resume=1'
  }

  return {
    savePendingIntent,
    getPendingIntent,
    clearPendingIntent,
    saveCheckoutDraft,
    getCheckoutDraft,
    clearCheckoutDraft,
    saveOrderSubmission,
    getOrderSubmission,
    clearOrderSubmission,
    savePendingOrder,
    getPendingOrder,
    clearPendingOrder,
    resumePath
  }
}

const defaultService = createMallIntentService()

module.exports = {
  createIdempotencyKey: newIdempotencyKey,
  paymentIdempotencyKey,
  createMallIntentService,
  savePendingIntent: defaultService.savePendingIntent,
  getPendingIntent: defaultService.getPendingIntent,
  clearPendingIntent: defaultService.clearPendingIntent,
  saveCheckoutDraft: defaultService.saveCheckoutDraft,
  getCheckoutDraft: defaultService.getCheckoutDraft,
  clearCheckoutDraft: defaultService.clearCheckoutDraft,
  saveOrderSubmission: defaultService.saveOrderSubmission,
  getOrderSubmission: defaultService.getOrderSubmission,
  clearOrderSubmission: defaultService.clearOrderSubmission,
  savePendingOrder: defaultService.savePendingOrder,
  getPendingOrder: defaultService.getPendingOrder,
  clearPendingOrder: defaultService.clearPendingOrder,
  resumePath: defaultService.resumePath
}

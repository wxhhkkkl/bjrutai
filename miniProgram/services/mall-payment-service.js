const { request } = require('./request-service')
const { getAccessToken } = require('./session-service')

function validationError(message) {
  const error = new Error(message)
  error.kind = 'VALIDATION'
  return error
}

function normalizeId(value, label = '商城编号') {
  const text = String(value === undefined || value === null ? '' : value).trim()
  if (!/^[1-9][0-9]*$/.test(text)) throw validationError(`${label}不合法`)
  return text
}

function normalizeKey(value) {
  const key = typeof value === 'string' ? value.trim() : ''
  if (key.length < 16 || key.length > 128) throw validationError('操作凭证不合法，请重新提交')
  return key
}

function authError() {
  const error = new Error('请先登录后继续支付')
  error.kind = 'AUTH'
  return error
}

function classifyPaymentState(order, payment) {
  const status = String((payment && payment.status) || (order && order.paymentStatus) || '')
  if (status === 'succeeded' || Number(order && order.paidAmountCent) > 0) return 'succeeded'
  if (status === 'closed' || (order && order.status === 'closed')) return 'closed'
  if (status === 'unknown' || status === 'creating' || status === 'abnormal') return 'unknown'
  if (status === 'pending' || status === 'processing' || status === 'prepared') return 'pending'
  if (status === 'failed') return 'failed'
  if (status === 'not_started' || !status) return 'not_started'
  return 'unknown'
}

function defaultRequestPayment(params) {
  if (typeof wx === 'undefined' || typeof wx.requestPayment !== 'function') {
    return Promise.reject(validationError('当前环境暂不支持微信支付'))
  }
  return new Promise((resolve, reject) => {
    wx.requestPayment({
      timeStamp: params.timeStamp,
      nonceStr: params.nonceStr,
      package: params.package,
      signType: params.signType,
      paySign: params.paySign,
      success: resolve,
      fail: reject
    })
  })
}

function isCancelled(error) {
  const message = String((error && (error.errMsg || error.message)) || '')
  return /cancel/i.test(message)
}

function defaultSleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function createMallPaymentService(options = {}) {
  const send = options.request || request
  const accessToken = options.getAccessToken || getAccessToken
  const invoke = options.requestPayment || defaultRequestPayment
  const sleep = options.sleep || defaultSleep
  const prepareWaitAttempts = Number.isInteger(options.prepareWaitAttempts) && options.prepareWaitAttempts > 0
    ? options.prepareWaitAttempts
    : 25
  const prepareWaitIntervalMs = Number.isInteger(options.prepareWaitIntervalMs) && options.prepareWaitIntervalMs >= 0
    ? options.prepareWaitIntervalMs
    : 800

  function requireBuyer() {
    if (!accessToken()) throw authError()
  }

  function orderPath(orderId) {
    return `/api/v1/mall/orders/${normalizeId(orderId, '订单编号')}`
  }

  function preparePayment(orderId, expectedVersion, key) {
    requireBuyer()
    if (!Number.isInteger(expectedVersion) || expectedVersion < 1) throw validationError('订单版本已变化，请刷新')
    return send(`${orderPath(orderId)}/payment`, {
      method: 'POST',
      data: { expectedVersion },
      idempotencyKey: normalizeKey(key)
    })
  }

  function getPayment(orderId) {
    requireBuyer()
    return send(`${orderPath(orderId)}/payment`)
  }

  function getOrder(orderId) {
    requireBuyer()
    return send(orderPath(orderId))
  }

  // Server-side prepay creation is asynchronous. Briefly wait for it so the
  // payer does not need a second tap on "查询支付状态" before the sheet opens.
  async function waitForPreparedPayment(orderId) {
    for (let attempt = 0; attempt < prepareWaitAttempts; attempt += 1) {
      let snapshot
      try {
        snapshot = await reconcilePayment(orderId)
      } catch (_) {
        return null
      }
      if (['pending', 'succeeded', 'closed', 'failed', 'not_started'].includes(snapshot.status)) {
        return snapshot
      }
      await sleep(prepareWaitIntervalMs)
    }
    return null
  }

  async function reconcilePayment(orderId) {
    const order = await getOrder(orderId)
    let payment = null
    if (order.paymentStatus && order.paymentStatus !== 'not_started') {
      try {
        payment = await getPayment(orderId)
      } catch (error) {
        // The order projection is still authoritative evidence if payment
        // detail has not propagated or the status endpoint is temporarily down.
        if (classifyPaymentState(order, null) === 'succeeded' || classifyPaymentState(order, null) === 'closed') {
          return { order, payment: null, status: classifyPaymentState(order, null) }
        }
        throw error
      }
    }
    return { order, payment, status: classifyPaymentState(order, payment) }
  }

  async function payOrder(orderId, expectedVersion, key) {
    requireBuyer()
    let prepared
    try {
      prepared = await preparePayment(orderId, expectedVersion, key)
    } catch (prepareError) {
      try {
        const recovered = await reconcilePayment(orderId)
        if (recovered.status !== 'not_started') return { ...recovered, canInvoke: false, requestPaymentOutcome: 'not_invoked' }
      } catch (_) {
        // A failed prepare with an unreachable query has an unknown outcome.
      }
      return {
        order: null,
        payment: null,
        status: 'unknown',
        canInvoke: false,
        requestPaymentOutcome: 'not_invoked',
        message: (prepareError && prepareError.message) || '支付状态确认中，请查询原订单'
      }
    }

    const invokable = (value) => Boolean(
      value && value.canInvoke === true && value.invokeParams && typeof value.invokeParams === 'object'
    )
    let canInvoke = invokable(prepared)
    if (!canInvoke) {
      const snapshot = await waitForPreparedPayment(orderId)
      if (snapshot && (snapshot.status === 'succeeded' || snapshot.status === 'closed')) {
        return { ...snapshot, canInvoke: false, requestPaymentOutcome: 'not_invoked' }
      }
      if (snapshot && snapshot.status === 'pending') {
        try {
          const refreshed = await preparePayment(orderId, expectedVersion, key)
          if (invokable(refreshed)) {
            prepared = refreshed
            canInvoke = true
          }
        } catch (_) {
          // Fall through to the authoritative reconcile below.
        }
      }
    }
    let requestPaymentOutcome = 'not_invoked'
    if (canInvoke) {
      try {
        await invoke(prepared.invokeParams)
        requestPaymentOutcome = 'submitted'
      } catch (error) {
        requestPaymentOutcome = isCancelled(error) ? 'cancelled' : 'failed'
      }
    }

    try {
      const recovered = await reconcilePayment(orderId)
      if (recovered.status === 'not_started' && requestPaymentOutcome === 'submitted') {
        recovered.status = 'unknown'
      }
      return { ...recovered, canInvoke, requestPaymentOutcome }
    } catch (error) {
      return {
        order: null,
        payment: null,
        status: 'unknown',
        canInvoke,
        requestPaymentOutcome,
        message: (error && error.message) || '支付状态确认中，请查询原订单'
      }
    }
  }

  return { preparePayment, getPayment, getOrder, reconcilePayment, payOrder }
}

const defaultService = createMallPaymentService()

module.exports = {
  classifyPaymentState,
  createMallPaymentService,
  preparePayment: defaultService.preparePayment,
  getPayment: defaultService.getPayment,
  getOrder: defaultService.getOrder,
  reconcilePayment: defaultService.reconcilePayment,
  payOrder: defaultService.payOrder
}

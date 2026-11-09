const { request } = require('./request-service')
const { getAccessToken } = require('./session-service')

const ORDER_STATUSES = new Set([
  'pending_payment',
  'pending_shipment',
  'pending_receipt',
  'completed',
  'closed'
])

function validationError(message) {
  const error = new Error(message)
  error.kind = 'VALIDATION'
  return error
}

function authError() {
  const error = new Error('请先登录后查看商城订单')
  error.kind = 'AUTH'
  return error
}

function normalizeId(value, label = '订单编号') {
  const id = String(value === undefined || value === null ? '' : value).trim()
  if (!/^[1-9][0-9]*$/.test(id)) throw validationError(`${label}不合法`)
  return id
}

function normalizeKey(value) {
  const key = typeof value === 'string' ? value.trim() : ''
  if (key.length < 16 || key.length > 128) throw validationError('操作凭证不合法，请重新提交')
  return key
}

function normalizeListOptions(options = {}) {
  const pageSize = options.pageSize === undefined ? 20 : options.pageSize
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
    throw validationError('分页数量必须为1到100的整数')
  }
  const data = { pageSize }
  if (options.cursor !== undefined && options.cursor !== null && options.cursor !== '') {
    const cursor = String(options.cursor)
    if (cursor.length > 2048) throw validationError('分页游标过长')
    data.cursor = cursor
  }
  if (options.status !== undefined && options.status !== null && options.status !== '') {
    if (!ORDER_STATUSES.has(options.status)) throw validationError('订单状态筛选不合法')
    data.status = options.status
  }
  return data
}

function createMallOrderService(options = {}) {
  const send = options.request || request
  const accessToken = options.getAccessToken || getAccessToken

  function requireBuyer() {
    if (!accessToken()) throw authError()
  }

  function listMyMallOrders(listOptions = {}) {
    requireBuyer()
    return send('/api/v1/mall/orders', { data: normalizeListOptions(listOptions) })
  }

  function getMyMallOrder(orderId) {
    requireBuyer()
    return send(`/api/v1/mall/orders/${encodeURIComponent(normalizeId(orderId))}`)
  }

  function getMyMallLogistics(orderId) {
    requireBuyer()
    return send(`/api/v1/mall/orders/${encodeURIComponent(normalizeId(orderId))}/logistics`)
  }

  function confirmMallReceipt(orderId, expectedVersion, idempotencyKey) {
    requireBuyer()
    const identity = normalizeId(orderId)
    if (!Number.isInteger(expectedVersion) || expectedVersion < 1) {
      throw validationError('订单状态已变化，请刷新后重试')
    }
    return send(`/api/v1/mall/orders/${encodeURIComponent(identity)}/confirm-receipt`, {
      method: 'POST',
      data: { expectedVersion },
      idempotencyKey: normalizeKey(idempotencyKey)
    })
  }

  return { listMyMallOrders, getMyMallOrder, getMyMallLogistics, confirmMallReceipt }
}

const service = createMallOrderService()

module.exports = {
  createMallOrderService,
  listMyMallOrders: service.listMyMallOrders,
  getMyMallOrder: service.getMyMallOrder,
  getMyMallLogistics: service.getMyMallLogistics,
  confirmMallReceipt: service.confirmMallReceipt
}

const { request } = require('./request-service')
const { getAccessToken } = require('./session-service')

const TAX_NO_PATTERN = /^[A-Za-z0-9]{8,32}$/
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const INVOICE_TYPES = new Set(['digital_normal', 'manual_special_request'])

function validationError(message) {
  const error = new Error(message)
  error.kind = 'VALIDATION'
  return error
}

function authError() {
  const error = new Error('请先登录后查看商城发票')
  error.kind = 'AUTH'
  return error
}

function normalizeId(value, label) {
  const id = String(value === undefined || value === null ? '' : value).trim()
  if (!/^[1-9][0-9]*$/.test(id)) throw validationError(`${label}不合法`)
  return id
}

function normalizeKey(value) {
  const key = typeof value === 'string' ? value.trim() : ''
  if (key.length < 16 || key.length > 128) throw validationError('操作凭证不合法，请重新提交')
  return key
}

function normalizeVersion(value) {
  if (!Number.isInteger(value) || value < 1) throw validationError('开票资料已变化，请刷新后重试')
  return value
}

function requiredText(value, label, maxLength) {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text || text.length > maxLength) throw validationError(`${label}长度不合法`)
  return text
}

function normalizeEmail(value) {
  if (value === undefined || value === null || value === '') return undefined
  const email = requiredText(value, '邮箱', 254)
  if (!EMAIL_PATTERN.test(email)) throw validationError('邮箱格式不正确')
  return email
}

function normalizeTaxNo(value) {
  if (value === undefined || value === null || value === '') return undefined
  const taxNo = requiredText(value, '纳税人识别号', 32)
  if (!TAX_NO_PATTERN.test(taxNo)) throw validationError('纳税人识别号格式不正确')
  return taxNo
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
  return data
}

function normalizeApplication(value = {}) {
  const buyerType = value.buyerType
  if (!['personal', 'company'].includes(buyerType)) throw validationError('开票主体类型不合法')
  if (!INVOICE_TYPES.has(value.invoiceType)) throw validationError('发票类型不合法')
  const title = requiredText(value.title, '发票抬头', 200)
  const consentVersion = typeof value.consentVersion === 'string' ? value.consentVersion.trim() : ''
  if (!consentVersion || consentVersion.length > 128) throw validationError('商城开票用途告知版本缺失，请刷新后重试')
  if (value.consentConfirmed !== true) throw validationError('请先确认开票资料用途')
  const taxNo = normalizeTaxNo(value.taxNo)
  const email = normalizeEmail(value.email)
  if (buyerType === 'company' && !taxNo) throw validationError('企业抬头请填写纳税人识别号')
  if (buyerType === 'personal' && taxNo) throw validationError('个人抬头无需填写纳税人识别号')

  const data = {
    orderId: normalizeId(value.orderId, '订单编号'),
    expectedOrderVersion: normalizeVersion(value.expectedOrderVersion),
    buyerType,
    title,
    invoiceType: value.invoiceType,
    consentVersion,
    consentConfirmed: true
  }
  if (taxNo) data.taxNo = taxNo
  if (email) data.email = email
  return data
}

function normalizePatch(value = {}) {
  const consentVersion = typeof value.consentVersion === 'string' ? value.consentVersion.trim() : ''
  if (!consentVersion || consentVersion.length > 128) throw validationError('商城开票用途告知版本缺失，请刷新后重试')
  if (value.consentConfirmed !== true) throw validationError('请先确认补充资料用途')
  const data = { expectedVersion: normalizeVersion(value.expectedVersion) }
  if (Object.hasOwn(value, 'title')) data.title = requiredText(value.title, '发票抬头', 200)
  if (Object.hasOwn(value, 'taxNo')) data.taxNo = normalizeTaxNo(value.taxNo) || null
  if (Object.hasOwn(value, 'email')) data.email = normalizeEmail(value.email) || null
  if (Object.keys(data).length === 1) throw validationError('请填写需要更正的开票资料')
  data.consentVersion = consentVersion
  data.consentConfirmed = true
  return data
}

function normalizeReasonAction(value = {}) {
  return {
    expectedVersion: normalizeVersion(value.expectedVersion),
    reason: requiredText(value.reason, '更正原因', 500)
  }
}

function createMallInvoiceService(options = {}) {
  const send = options.request || request
  const accessToken = options.getAccessToken || getAccessToken

  function requireBuyer() {
    if (!accessToken()) throw authError()
  }

  function listMyMallInvoices(orderId, listOptions = {}) {
    requireBuyer()
    const identity = normalizeId(orderId, '订单编号')
    return send(`/api/v1/mall/orders/${encodeURIComponent(identity)}/invoices`, {
      data: normalizeListOptions(listOptions)
    })
  }

  function createMallInvoiceRequest(application, idempotencyKey) {
    requireBuyer()
    return send('/api/v1/mall/invoice-requests', {
      method: 'POST',
      data: normalizeApplication(application),
      idempotencyKey: normalizeKey(idempotencyKey)
    })
  }

  function getMyMallInvoiceRequest(requestId) {
    requireBuyer()
    const identity = normalizeId(requestId, '开票申请编号')
    return send(`/api/v1/mall/invoice-requests/${encodeURIComponent(identity)}`)
  }

  function updateMallInvoiceRequest(requestId, changes, idempotencyKey) {
    requireBuyer()
    const identity = normalizeId(requestId, '开票申请编号')
    return send(`/api/v1/mall/invoice-requests/${encodeURIComponent(identity)}`, {
      method: 'PATCH',
      data: normalizePatch(changes),
      idempotencyKey: normalizeKey(idempotencyKey)
    })
  }

  function withdrawMallInvoiceRequest(requestId, action, idempotencyKey) {
    requireBuyer()
    const identity = normalizeId(requestId, '开票申请编号')
    return send(`/api/v1/mall/invoice-requests/${encodeURIComponent(identity)}/withdraw`, {
      method: 'POST',
      data: normalizeReasonAction(action),
      idempotencyKey: normalizeKey(idempotencyKey)
    })
  }

  function requestMallInvoiceCorrection(invoiceId, action, idempotencyKey) {
    requireBuyer()
    const identity = normalizeId(invoiceId, '发票编号')
    return send(`/api/v1/mall/invoices/${encodeURIComponent(identity)}/correction`, {
      method: 'POST',
      data: normalizeReasonAction(action),
      idempotencyKey: normalizeKey(idempotencyKey)
    })
  }

  function getMallInvoiceFileAccess(fileId) {
    requireBuyer()
    const identity = normalizeId(fileId, '票据文件编号')
    // The API returns a 60-second private link. Always fetch again for retry; never persist it here.
    return send(`/api/v1/mall/files/${encodeURIComponent(identity)}/access`)
  }

  return {
    listMyMallInvoices,
    createMallInvoiceRequest,
    getMyMallInvoiceRequest,
    updateMallInvoiceRequest,
    withdrawMallInvoiceRequest,
    requestMallInvoiceCorrection,
    getMallInvoiceFileAccess
  }
}

const service = createMallInvoiceService()

module.exports = {
  createMallInvoiceService,
  listMyMallInvoices: service.listMyMallInvoices,
  createMallInvoiceRequest: service.createMallInvoiceRequest,
  getMyMallInvoiceRequest: service.getMyMallInvoiceRequest,
  updateMallInvoiceRequest: service.updateMallInvoiceRequest,
  withdrawMallInvoiceRequest: service.withdrawMallInvoiceRequest,
  requestMallInvoiceCorrection: service.requestMallInvoiceCorrection,
  getMallInvoiceFileAccess: service.getMallInvoiceFileAccess
}

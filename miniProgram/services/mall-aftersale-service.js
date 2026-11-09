const { request } = require('./request-service')
const { getAccessToken } = require('./session-service')
const { uploadToCos } = require('./cos-upload')
const { sha256Hex } = require('../utils/sha256')

const RETURN_CODE_PATTERN = /^[A-Za-z0-9_-]+$/
const REFUND_STATUSES = new Set(['prepared', 'processing', 'unknown', 'abnormal', 'succeeded', 'closed'])

function validationError(message) {
  const error = new Error(message)
  error.kind = 'VALIDATION'
  return error
}

function authError() {
  const error = new Error('请先登录后查看或处理售后')
  error.kind = 'AUTH'
  return error
}

function normalizeId(value, label = '商城编号') {
  const text = typeof value === 'number' ? String(value) : String(value || '').trim()
  if (!/^[1-9][0-9]*$/.test(text)) throw validationError(`${label}不合法`)
  return text
}

function normalizeIdempotencyKey(value) {
  const key = typeof value === 'string' ? value.trim() : ''
  if (key.length < 16 || key.length > 128) throw validationError('操作凭证不合法，请重新提交')
  return key
}

function requiredText(value, label, maxLength) {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text || text.length > maxLength) throw validationError(`${label}长度不合法`)
  return text
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
  const method = value.method
  const scope = value.scope || 'goods'
  if (!['refund_only', 'return_refund'].includes(method)) throw validationError('售后方式不合法')
  if (!['goods', 'freight_only'].includes(scope)) throw validationError('售后范围不合法')

  const lines = Array.isArray(value.items) ? value.items : []
  if (lines.length > 50 || (scope === 'goods' && lines.length === 0)) {
    throw validationError('申请商品明细数量不合法')
  }
  const items = lines.map((line) => {
    if (!Number.isInteger(line.quantity) || line.quantity < 1 || line.quantity > 999) {
      throw validationError('申请数量必须为1到999的整数')
    }
    return { orderItemId: normalizeId(line.orderItemId, '订单商品编号'), quantity: line.quantity }
  })
  if (new Set(items.map((line) => line.orderItemId)).size !== items.length) {
    throw validationError('同一订单商品明细不能重复')
  }

  if (scope === 'freight_only' && (items.length || method !== 'refund_only')) {
    throw validationError('仅运费申请不能包含商品或退货')
  }

  const reason = requiredText(value.reason, '售后原因', 200)
  const description = typeof value.description === 'string' ? value.description.trim() : ''
  if (description.length > 1000) throw validationError('补充说明不能超过1000个字符')
  const proofFileIds = Array.isArray(value.proofFileIds) ? value.proofFileIds.map((id) => normalizeId(id, '凭证编号')) : []
  if (proofFileIds.length > 3 || new Set(proofFileIds).size !== proofFileIds.length) {
    throw validationError('凭证最多3个且不能重复')
  }

  if (!Number.isInteger(value.expectedOrderVersion) || value.expectedOrderVersion < 1) {
    throw validationError('订单版本不合法，请刷新后重试')
  }

  return {
    orderId: normalizeId(value.orderId, '订单编号'),
    expectedOrderVersion: value.expectedOrderVersion,
    method,
    items,
    reason,
    description,
    proofFileIds,
    scope
  }
}

function normalizeVersion(value) {
  if (!Number.isInteger(value) || value < 1) throw validationError('售后版本不合法，请刷新后重试')
  return value
}

function normalizeProofMetadata(value = {}) {
  const fileName = requiredText(value.fileName, '文件名', 255)
  if (/[\\/\u0000-\u001f]/.test(fileName)) throw validationError('文件名不合法')
  if (!['image/jpeg', 'image/png'].includes(value.contentType)) throw validationError('售后凭证仅支持JPG或PNG图片')
  if (!Number.isInteger(value.fileSize) || value.fileSize < 1 || value.fileSize > 5 * 1024 * 1024) {
    throw validationError('图片不能超过5MB')
  }
  if (typeof value.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(value.sha256)) {
    throw validationError('图片校验摘要不合法')
  }
  return {
    purpose: 'aftersale_proof',
    orderId: normalizeId(value.orderId, '订单编号'),
    fileName,
    contentType: value.contentType,
    fileSize: value.fileSize,
    sha256: value.sha256
  }
}

function defaultReadFile(filePath) {
  return new Promise((resolve, reject) => {
    if (typeof wx === 'undefined' || !wx.getFileSystemManager) {
      reject(validationError('当前环境无法读取本地图片'))
      return
    }
    wx.getFileSystemManager().readFile({
      filePath,
      success(result) { resolve(result.data) },
      fail() { reject(validationError('无法读取售后凭证图片')) }
    })
  })
}

function byteLength(value) {
  if (value instanceof ArrayBuffer) return value.byteLength
  if (ArrayBuffer.isView(value)) return value.byteLength
  throw validationError('本地图片读取结果不合法')
}

function createMallAftersaleService(options = {}) {
  const send = options.request || request
  const readFile = options.readFileAdapter || defaultReadFile
  const upload = options.uploadAdapter
  const accessToken = options.getAccessToken || getAccessToken

  function requireBuyer() {
    if (!accessToken()) throw authError()
  }

  function uploadResponse(result) {
    const statusCode = Number(result && result.statusCode) || 0
    if (statusCode < 200 || statusCode >= 300) throw validationError('售后凭证上传失败，请重新核验后重试')
    return result
  }

  function listMyMallAftersales(listOptions = {}) {
    requireBuyer()
    return send('/api/v1/mall/aftersales', { data: normalizeListOptions(listOptions) })
  }

  function getMyMallAftersale(aftersaleId) {
    requireBuyer()
    return send(`/api/v1/mall/aftersales/${encodeURIComponent(normalizeId(aftersaleId, '售后编号'))}`)
  }

  function createMallAftersale(application, idempotencyKey) {
    requireBuyer()
    return send('/api/v1/mall/aftersales', {
      method: 'POST',
      data: normalizeApplication(application),
      idempotencyKey: normalizeIdempotencyKey(idempotencyKey)
    })
  }

  function withdrawMallAftersale(aftersaleId, action = {}, idempotencyKey) {
    requireBuyer()
    const data = {
      expectedVersion: normalizeVersion(action.expectedVersion),
      reason: requiredText(action.reason, '撤回原因', 500)
    }
    return send(`/api/v1/mall/aftersales/${encodeURIComponent(normalizeId(aftersaleId, '售后编号'))}/withdraw`, {
      method: 'POST', data, idempotencyKey: normalizeIdempotencyKey(idempotencyKey)
    })
  }

  function sendMallReturn(aftersaleId, shipment = {}, idempotencyKey) {
    requireBuyer()
    const courierCode = requiredText(shipment.courierCode, '快递公司编码', 32)
    const trackingNo = requiredText(shipment.trackingNo, '退货运单号', 64)
    if (!RETURN_CODE_PATTERN.test(courierCode) || courierCode.length < 1) throw validationError('快递公司编码不合法')
    if (!RETURN_CODE_PATTERN.test(trackingNo) || trackingNo.length < 4) throw validationError('退货运单号不合法')
    const data = { expectedVersion: normalizeVersion(shipment.expectedVersion), courierCode, trackingNo }
    return send(`/api/v1/mall/aftersales/${encodeURIComponent(normalizeId(aftersaleId, '售后编号'))}/return-shipment`, {
      method: 'POST', data, idempotencyKey: normalizeIdempotencyKey(idempotencyKey)
    })
  }

  async function getAftersaleProofUploadTicket(metadata, idempotencyKey) {
    requireBuyer()
    const source = metadata || {}
    const filePath = typeof source.filePath === 'string' ? source.filePath.trim() : ''
    let value = source
    if (filePath) {
      let bytes
      try {
        bytes = await readFile(filePath)
      } catch (error) {
        if (error && error.kind) throw error
        throw validationError('无法读取售后凭证图片')
      }
      const actualSize = byteLength(bytes)
      if (source.fileSize !== undefined && source.fileSize !== actualSize) {
        throw validationError('图片大小已变化，请重新选择')
      }
      value = { ...source, fileSize: actualSize, sha256: sha256Hex(bytes) }
    }
    return send('/api/v1/mall/files/upload-ticket', {
      method: 'POST', data: normalizeProofMetadata(value),
      idempotencyKey: normalizeIdempotencyKey(idempotencyKey)
    })
  }

  async function uploadAftersaleProofFile(uploadUrl, filePath, contentType) {
    requireBuyer()
    const target = typeof uploadUrl === 'string' ? uploadUrl.trim() : ''
    const localPath = typeof filePath === 'string' ? filePath.trim() : ''
    if (!/^https:\/\/[a-z0-9-]+\.cos\.[a-z0-9-]+\.myqcloud\.com\/[^\s?#]+(?:\?[^\s#]*)?$/i.test(target) || !localPath) {
      throw validationError('图片上传凭证不合法')
    }
    if (!['image/jpeg', 'image/png'].includes(contentType)) throw validationError('售后凭证仅支持JPG或PNG图片')
    try {
      if (upload && readFile) {
        const data = await readFile(localPath)
        return uploadResponse(await upload(target, localPath, contentType, data))
      }
      return await uploadToCos({ uploadUrl: target }, localPath, contentType, '售后凭证')
    } catch (error) {
      if (error && error.kind) throw error
      throw validationError('售后凭证上传失败，请检查网络后重试')
    }
  }

  function verifyAftersaleProof(fileId, idempotencyKey) {
    requireBuyer()
    const identity = normalizeId(fileId, '凭证编号')
    return send(`/api/v1/mall/files/${encodeURIComponent(identity)}/verify`, {
      method: 'POST', idempotencyKey: normalizeIdempotencyKey(idempotencyKey)
    })
  }

  function getFinancialProgress(value = {}) {
    const refundStatus = REFUND_STATUSES.has(value.refundStatus) ? value.refundStatus : 'not_exposed'
    const invoiceStatus = typeof value.invoiceStatus === 'string' && value.invoiceStatus.trim()
      ? value.invoiceStatus.trim()
      : 'not_exposed'
    return {
      aftersaleStatus: typeof value.status === 'string' ? value.status : 'not_exposed',
      refundId: value.refundId ? normalizeId(value.refundId, '退款编号') : null,
      refundStatus,
      invoiceStatus
    }
  }

  return {
    listMyMallAftersales,
    getMyMallAftersale,
    createMallAftersale,
    withdrawMallAftersale,
    sendMallReturn,
    getAftersaleProofUploadTicket,
    uploadAftersaleProofFile,
    verifyAftersaleProof,
    getFinancialProgress
  }
}

const service = createMallAftersaleService()

module.exports = {
  createMallAftersaleService,
  listMyMallAftersales: service.listMyMallAftersales,
  getMyMallAftersale: service.getMyMallAftersale,
  createMallAftersale: service.createMallAftersale,
  withdrawMallAftersale: service.withdrawMallAftersale,
  sendMallReturn: service.sendMallReturn,
  getAftersaleProofUploadTicket: service.getAftersaleProofUploadTicket,
  uploadAftersaleProofFile: service.uploadAftersaleProofFile,
  verifyAftersaleProof: service.verifyAftersaleProof,
  getFinancialProgress: service.getFinancialProgress
}

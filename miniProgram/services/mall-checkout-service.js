const { request } = require('./request-service')
const { getAccessToken } = require('./session-service')

function validationError(message) {
  const error = new Error(message)
  error.kind = 'VALIDATION'
  return error
}

function authError() {
  const error = new Error('请先登录后继续商城结算')
  error.kind = 'AUTH'
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

function normalizePage(options = {}) {
  const pageSize = options.pageSize === undefined ? 20 : options.pageSize
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
    throw validationError('分页数量必须为1到100的整数')
  }
  const data = { pageSize }
  if (options.cursor) {
    const cursor = String(options.cursor)
    if (cursor.length > 2048) throw validationError('分页游标过长')
    data.cursor = cursor
  }
  return data
}

function normalizeItems(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 50) {
    throw validationError('结算商品数量不合法')
  }
  const items = value.map((line) => {
    const quantity = line && line.quantity
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 999) {
      throw validationError('商品数量必须为1到999的整数')
    }
    return { skuId: normalizeId(line.skuId, '商品规格编号'), quantity }
  })
  if (new Set(items.map((line) => line.skuId)).size !== items.length) {
    throw validationError('相同商品规格不能重复，请合并数量')
  }
  return items
}

function addressFields(value) {
  const input = value || {}
  const recipientName = typeof input.recipientName === 'string' ? input.recipientName.trim() : ''
  const phone = typeof input.phone === 'string' ? input.phone.trim() : ''
  const addressLine = typeof input.addressLine === 'string' ? input.addressLine.trim() : ''
  if (!recipientName || recipientName.length > 50) throw validationError('收件人姓名长度不合法')
  if (!/^1[3-9][0-9]{9}$/.test(phone)) throw validationError('手机号格式不正确')
  if (!addressLine || addressLine.length > 200) throw validationError('详细地址长度不合法')
  const regionCodes = input.regionCodes
  if (!Array.isArray(regionCodes) || regionCodes.length !== 3 || regionCodes.some((code) => !/^[0-9]{6}$/.test(String(code)))) {
    throw validationError('请完整选择省、市、区地区编码')
  }
  const consentVersion = typeof input.consentVersion === 'string' ? input.consentVersion.trim() : ''
  if (!consentVersion || consentVersion.length > 128) throw validationError('商城资料说明版本缺失，请刷新后重试')
  if (input.consentConfirmed !== true) throw validationError('请确认收件资料用途后再保存')
  const result = {
    recipientName,
    phone,
    regionCodes: regionCodes.map(String),
    addressLine,
    isDefault: Boolean(input.isDefault),
    consentVersion,
    consentConfirmed: true
  }
  if (Array.isArray(input.regionNames)) {
    if (input.regionNames.length !== 3 || input.regionNames.some((name) => typeof name !== 'string' || !name.trim() || name.trim().length > 20)) {
      throw validationError('地区名称不合法，请重新选择地区')
    }
    result.regionNames = input.regionNames.map((name) => name.trim())
  }
  return result
}

function createMallCheckoutService(options = {}) {
  const send = options.request || request
  const accessToken = options.getAccessToken || getAccessToken

  function requireBuyer() {
    if (!accessToken()) throw authError()
  }

  function getCheckoutSettings() {
    return send('/api/v1/mall/checkout/settings', { auth: false })
  }

  function listAddresses(page = {}) {
    requireBuyer()
    return send('/api/v1/mall/addresses', { data: normalizePage(page) })
  }

  function createAddress(value, key) {
    requireBuyer()
    if (!value || value.consentConfirmed !== true) {
      throw validationError('请确认收货资料仅用于商城订单履约')
    }
    return send('/api/v1/mall/addresses', {
      method: 'POST',
      data: addressFields(value),
      idempotencyKey: normalizeKey(key)
    })
  }

  function updateAddress(addressId, value, key) {
    requireBuyer()
    const identity = normalizeId(addressId, '地址编号')
    const input = value || {}
    if (!Number.isInteger(input.expectedVersion) || input.expectedVersion < 1) {
      throw validationError('地址版本已变化，请刷新后重试')
    }
    const data = { expectedVersion: input.expectedVersion }
    if (Object.prototype.hasOwnProperty.call(input, 'recipientName')) {
      const name = typeof input.recipientName === 'string' ? input.recipientName.trim() : ''
      if (!name || name.length > 50) throw validationError('收件人姓名长度不合法')
      data.recipientName = name
    }
    if (Object.prototype.hasOwnProperty.call(input, 'phone')) {
      const phone = typeof input.phone === 'string' ? input.phone.trim() : ''
      if (!/^1[3-9][0-9]{9}$/.test(phone)) throw validationError('手机号格式不正确')
      data.phone = phone
    }
    if (Object.prototype.hasOwnProperty.call(input, 'regionCodes')) {
      if (!Array.isArray(input.regionCodes) || input.regionCodes.length !== 3 || input.regionCodes.some((code) => !/^[0-9]{6}$/.test(String(code)))) {
        throw validationError('请完整选择省、市、区地区编码')
      }
      data.regionCodes = input.regionCodes.map(String)
    }
    if (Object.prototype.hasOwnProperty.call(input, 'regionNames')) {
      if (!Array.isArray(input.regionNames) || input.regionNames.length !== 3 || input.regionNames.some((name) => typeof name !== 'string' || !name.trim() || name.trim().length > 20)) {
        throw validationError('地区名称不合法，请重新选择地区')
      }
      data.regionNames = input.regionNames.map((name) => name.trim())
    }
    if (Object.prototype.hasOwnProperty.call(input, 'addressLine')) {
      const addressLine = typeof input.addressLine === 'string' ? input.addressLine.trim() : ''
      if (!addressLine || addressLine.length > 200) throw validationError('详细地址长度不合法')
      data.addressLine = addressLine
    }
    if (Object.prototype.hasOwnProperty.call(input, 'isDefault')) data.isDefault = Boolean(input.isDefault)
    if (Object.keys(data).length === 1) throw validationError('请先修改地址信息')
    return send(`/api/v1/mall/addresses/${identity}`, {
      method: 'PATCH', data, idempotencyKey: normalizeKey(key)
    })
  }

  function archiveAddress(addressId, expectedVersion, key) {
    requireBuyer()
    const identity = normalizeId(addressId, '地址编号')
    if (!Number.isInteger(expectedVersion) || expectedVersion < 1) throw validationError('地址版本不合法')
    return send(`/api/v1/mall/addresses/${identity}/archive`, {
      method: 'POST', data: { expectedVersion }, idempotencyKey: normalizeKey(key)
    })
  }

  function getCart(page = {}) {
    requireBuyer()
    return send('/api/v1/mall/cart', { data: normalizePage(page) })
  }

  function addToCart(skuId, quantity, key) {
    requireBuyer()
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 999) throw validationError('商品数量必须为1到999的整数')
    return send('/api/v1/mall/cart', {
      method: 'POST',
      data: { skuId: normalizeId(skuId, '商品规格编号'), quantity },
      idempotencyKey: normalizeKey(key)
    })
  }

  function updateCartItem(cartItemId, quantity, expectedVersion, key) {
    requireBuyer()
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 999) throw validationError('商品数量必须为1到999的整数')
    if (!Number.isInteger(expectedVersion) || expectedVersion < 1) throw validationError('购物车版本已变化，请刷新')
    return send(`/api/v1/mall/cart/${normalizeId(cartItemId, '购物车编号')}`, {
      method: 'PATCH',
      data: { quantity, expectedVersion },
      idempotencyKey: normalizeKey(key)
    })
  }

  function removeCartItem(cartItemId, expectedVersion, key) {
    requireBuyer()
    if (!Number.isInteger(expectedVersion) || expectedVersion < 1) throw validationError('购物车版本已变化，请刷新')
    return send(`/api/v1/mall/cart/${normalizeId(cartItemId, '购物车编号')}/remove`, {
      method: 'POST',
      data: { expectedVersion },
      idempotencyKey: normalizeKey(key)
    })
  }

  function quoteOrder(value) {
    requireBuyer()
    const addressId = value && value.addressId ? normalizeId(value.addressId, '收货地址编号') : ''
    return send('/api/v1/mall/checkout/quote', {
      method: 'POST',
      data: { ...(addressId ? { addressId } : {}), items: normalizeItems(value && value.items) }
    })
  }

  function createOrder(value, key) {
    requireBuyer()
    const quoteToken = typeof (value && value.quoteToken) === 'string' ? value.quoteToken : ''
    const consentVersion = typeof (value && value.consentVersion) === 'string' ? value.consentVersion : ''
    if (!quoteToken || quoteToken.length > 32768) throw validationError('报价已失效，请重新确认')
    if (!consentVersion || consentVersion.length > 128) throw validationError('商城规则版本缺失，请刷新后重试')
    const buyerNote = value && typeof value.buyerNote === 'string' ? value.buyerNote.trim() : ''
    if (buyerNote.length > 200) throw validationError('订单备注不能超过200个字符')
    return send('/api/v1/mall/orders', {
      method: 'POST',
      data: {
        quoteToken,
        consentVersion,
        consentConfirmed: Boolean(value && value.consentConfirmed === true),
        buyerNote,
        invoiceIntent: Boolean(value && value.invoiceIntent)
      },
      idempotencyKey: normalizeKey(key)
    })
  }

  function getOrder(orderId) {
    requireBuyer()
    return send(`/api/v1/mall/orders/${normalizeId(orderId, '订单编号')}`)
  }

  return {
    getCheckoutSettings,
    listAddresses,
    createAddress,
    updateAddress,
    archiveAddress,
    getCart,
    addToCart,
    updateCartItem,
    removeCartItem,
    quoteOrder,
    createOrder,
    getOrder
  }
}

const defaultService = createMallCheckoutService()

module.exports = {
  createMallCheckoutService,
  getCheckoutSettings: defaultService.getCheckoutSettings,
  listAddresses: defaultService.listAddresses,
  createAddress: defaultService.createAddress,
  updateAddress: defaultService.updateAddress,
  archiveAddress: defaultService.archiveAddress,
  getCart: defaultService.getCart,
  addToCart: defaultService.addToCart,
  updateCartItem: defaultService.updateCartItem,
  removeCartItem: defaultService.removeCartItem,
  quoteOrder: defaultService.quoteOrder,
  createOrder: defaultService.createOrder,
  getOrder: defaultService.getOrder
}

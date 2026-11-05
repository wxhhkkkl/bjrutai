const { request } = require('./request-service')

function id(value) {
  const text = String(value)
  if (!/^[1-9][0-9]*$/.test(text)) throw new Error('商城编号不合法')
  return text
}

function pagination(options) {
  const pageSize = options.pageSize === undefined ? 20 : options.pageSize
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) throw new Error('分页数量必须为1到100的整数')
  const data = { pageSize }
  if (options.cursor) data.cursor = String(options.cursor)
  return data
}

function listCategories(options = {}) {
  return request('/api/v1/mall/categories', { auth: false, data: pagination(options) })
}

function listProducts(options = {}) {
  const data = pagination(options)
  if (options.categoryId) data.categoryId = id(options.categoryId)
  if (options.q) {
    data.q = String(options.q).trim()
    if (data.q.length > 128) throw new Error('搜索内容过长')
  }
  if (options.sort) {
    if (!['default', 'price_asc', 'price_desc'].includes(options.sort)) throw new Error('排序方式不合法')
    data.sort = options.sort
  }
  return request('/api/v1/mall/products', { auth: false, data })
}

function getProduct(productId) {
  return request(`/api/v1/mall/products/${id(productId)}`, { auth: false })
}

function productAvailability(product) {
  if (!product || product.status !== 'on_sale') return 'off_sale'
  return Array.isArray(product.skus) && product.skus.some(s => s.stockStatus === 'available')
    ? 'available' : 'sold_out'
}

function catalogViewState(page, error) {
  if (error) return error.statusCode === 403 || error.httpStatus === 403 ? 'forbidden' : 'recoverable-error'
  if (!page) return 'loading'
  return Array.isArray(page.items) && page.items.length ? 'success' : 'empty'
}

module.exports = { listCategories, listProducts, getProduct, productAvailability, catalogViewState }

const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function fixture() {
  const target = path.resolve(__dirname, '../../services/mall-catalog-service.js')
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const original = require.cache[requestPath]
  const calls = []
  delete require.cache[target]
  require.cache[requestPath] = { id: requestPath, filename: requestPath, loaded: true,
    exports: { request(apiPath, options) { calls.push({ apiPath, options }); return Promise.resolve({ items: [] }) } } }
  return { service: require(target), calls, restore() {
    delete require.cache[target]
    if (original) require.cache[requestPath] = original
    else delete require.cache[requestPath]
  } }
}

test('mall catalog uses public authenticated-free contracts and real query parameters', async () => {
  const f = fixture()
  try {
    await f.service.listCategories({ pageSize: 20 })
    await f.service.listProducts({ categoryId: '9', q: ' 燕麦 ', sort: 'price_asc', cursor: 'next' })
    await f.service.getProduct('18')
    assert.deepEqual(f.calls, [
      { apiPath: '/api/v1/mall/categories', options: { auth: false, data: { pageSize: 20 } } },
      { apiPath: '/api/v1/mall/products', options: { auth: false, data: { pageSize: 20, categoryId: '9', q: '燕麦', sort: 'price_asc', cursor: 'next' } } },
      { apiPath: '/api/v1/mall/products/18', options: { auth: false } }
    ])
  } finally { f.restore() }
})

test('mall catalog rejects invalid IDs, float page sizes and unknown sorting before transport', () => {
  const f = fixture()
  try {
    assert.throws(() => f.service.getProduct('../other'))
    assert.throws(() => f.service.listProducts({ pageSize: 1.5 }))
    assert.throws(() => f.service.listProducts({ sort: 'marketing' }))
    assert.equal(f.calls.length, 0)
  } finally { f.restore() }
})

test('catalog state shows sold-out separately and never invents fallback products', () => {
  const f = fixture()
  try {
    assert.equal(f.service.productAvailability({ status: 'on_sale', skus: [{ stockStatus: 'sold_out' }] }), 'sold_out')
    assert.equal(f.service.productAvailability({ status: 'off_sale', skus: [{ stockStatus: 'available' }] }), 'off_sale')
    assert.equal(f.service.productAvailability({ status: 'on_sale', skus: [{ stockStatus: 'available' }] }), 'available')
    assert.equal(f.service.catalogViewState({ items: [] }), 'empty')
    assert.equal(f.service.catalogViewState(null, { statusCode: 403 }), 'forbidden')
    assert.equal(f.service.catalogViewState(null, new Error('network')), 'recoverable-error')
  } finally { f.restore() }
})

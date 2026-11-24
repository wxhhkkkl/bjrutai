const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function loadPage(relativePath, service) {
  const pagePath = path.resolve(__dirname, '../../', relativePath)
  const servicePath = path.resolve(__dirname, '../../services/mall-catalog-service.js')
  const originalService = require.cache[servicePath]
  const originalPage = global.Page
  const originalWx = global.wx
  let definition
  const navigations = []

  delete require.cache[pagePath]
  const catalogHelpers = {
    productAvailability(product) {
      if (!product || product.status !== 'on_sale') return 'off_sale'
      return Array.isArray(product.skus) && product.skus.some((sku) => sku.stockStatus === 'available')
        ? 'available'
        : 'sold_out'
    },
    catalogViewState(page, error) {
      if (error) return error.httpStatus === 403 || error.statusCode === 403 ? 'forbidden' : 'recoverable-error'
      if (!page) return 'loading'
      return Array.isArray(page.items) && page.items.length ? 'success' : 'empty'
    }
  }
  require.cache[servicePath] = {
    id: servicePath,
    filename: servicePath,
    loaded: true,
    exports: Object.assign(catalogHelpers, service)
  }
  global.Page = (value) => { definition = value }
  global.wx = {
    navigateTo(options) { navigations.push(options.url) },
    navigateBack() {},
    stopPullDownRefresh() {},
    showToast() {}
  }
  require(pagePath)

  const page = Object.assign({}, definition, {
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(values, callback) {
      this.data = Object.assign({}, this.data, values)
      if (callback) callback()
    }
  })
  return {
    page,
    navigations,
    restore() {
      delete require.cache[pagePath]
      if (originalService) require.cache[servicePath] = originalService
      else delete require.cache[servicePath]
      global.Page = originalPage
      global.wx = originalWx
    }
  }
}

const categories = {
  items: [{ id: '5', name: '家庭护理', status: 'enabled', sort: 1 }],
  nextCursor: null,
  total: 1
}

const firstProduct = {
  id: '41',
  categoryId: '5',
  name: '家庭健康管理套装',
  summary: '日常健康管理用品',
  description: '商品说明内容',
  instructions: '使用说明内容',
  status: 'on_sale',
  coverUrl: 'https://image.example.test/product.jpg',
  galleryUrls: [],
  skus: [
    { id: '101', skuCode: 'S-1', options: [{ name: '规格', value: '标准装' }], priceCent: 990, stockStatus: 'available', availableQuantity: 2 },
    { id: '102', skuCode: 'S-2', options: [{ name: '规格', value: '组合装' }], priceCent: 2990, stockStatus: 'sold_out', availableQuantity: 0 }
  ]
}

test('mall catalog loads live categories and products with real prices and availability', async () => {
  const calls = []
  const fixture = loadPage('pages/mall/index.js', {
    listCategories(options) { calls.push(['categories', options]); return Promise.resolve(categories) },
    listProducts(options) { calls.push(['products', options]); return Promise.resolve({ items: [firstProduct], nextCursor: null, total: 1 }) }
  })
  try {
    fixture.page.onLoad()
    await flush()
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.products[0].name, firstProduct.name)
    assert.equal(fixture.page.data.products[0].priceText, '9.90')
    assert.equal(fixture.page.data.products[0].availability, 'available')
    assert.deepEqual(calls, [
      ['categories', { pageSize: 100 }],
      ['products', { pageSize: 20, sort: 'default' }]
    ])
  } finally { fixture.restore() }
})

test('mall search, category selection, price sort and cursor pagination use supported filters', async () => {
  const calls = []
  const fixture = loadPage('pages/mall/index.js', {
    listCategories() { return Promise.resolve(categories) },
    listProducts(options) {
      calls.push(options)
      return Promise.resolve({ items: [firstProduct], nextCursor: options.cursor ? null : 'cursor-1', total: 2 })
    }
  })
  try {
    fixture.page.onLoad()
    await flush()
    fixture.page.onSearchInput({ detail: { value: '健康套装' } })
    fixture.page.submitSearch()
    await flush()
    fixture.page.togglePriceSort()
    await flush()
    fixture.page.togglePriceSort()
    await flush()
    fixture.page.openCategoryFilter()
    fixture.page.selectCategory({ currentTarget: { dataset: { id: '5', name: '家庭护理' } } })
    await flush()
    fixture.page.onReachBottom()
    await flush()

    assert.deepEqual(calls.slice(1, 5), [
      { pageSize: 20, sort: 'default', q: '健康套装' },
      { pageSize: 20, sort: 'price_asc', q: '健康套装' },
      { pageSize: 20, sort: 'price_desc', q: '健康套装' },
      { pageSize: 20, sort: 'price_desc', categoryId: '5', q: '健康套装' }
    ])
    assert.equal(calls.at(-1).cursor, 'cursor-1')
    assert.equal(calls.at(-1).categoryId, '5')
    assert.equal(fixture.page.data.selectedCategoryName, '家庭护理')
  } finally { fixture.restore() }
})

test('catalog distinguishes empty, forbidden and recoverable errors and can retry', async () => {
  let fail = true
  const fixture = loadPage('pages/mall/index.js', {
    listCategories() { return Promise.resolve(categories) },
    listProducts() {
      if (fail) return Promise.reject({ httpStatus: 503, message: '网络暂不可用' })
      return Promise.resolve({ items: [], nextCursor: null, total: 0 })
    }
  })
  try {
    fixture.page.onLoad()
    await flush()
    assert.equal(fixture.page.data.state, 'recoverable-error')
    fail = false
    fixture.page.retry()
    await flush()
    assert.equal(fixture.page.data.state, 'empty')
    assert.match(fixture.page.data.stateMessage, /商品/)
  } finally { fixture.restore() }
})

test('product detail loads current SKU prices and exposes sold-out variants without fake original prices', async () => {
  const calls = []
  const fixture = loadPage('pages/mall-product/index.js', {
    getProduct(id) { calls.push(id); return Promise.resolve(firstProduct) }
  })
  try {
    fixture.page.onLoad({ id: '41' })
    await flush()
    assert.deepEqual(calls, ['41'])
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.product.name, firstProduct.name)
    assert.equal(fixture.page.data.skus[0].priceText, '9.90')
    assert.equal(fixture.page.data.skus[0].availabilityText, '库存 2 件')
    assert.equal(fixture.page.data.skus[1].availability, 'sold_out')
    assert.equal(fixture.page.data.skus[1].availabilityText, '暂时售罄')
    assert.equal(fixture.page.data.availabilityText, '库存 2 件')
    fixture.page.selectSku({ currentTarget: { dataset: { id: '102' } } })
    assert.equal(fixture.page.data.selectedSkuId, '102')
    assert.equal(fixture.page.data.availabilityText, '暂时售罄')
  } finally { fixture.restore() }
})

test('product detail makes rich-text description images fit the content width', async () => {
  const richProduct = {
    ...firstProduct,
    id: '43',
    description: '<!--mall-rich-text--><p><img src="https://image.example.test/detail.jpg" alt="商品详情图片" width="1500" height="2000" style="border-radius: 8px"></p>'
  }
  const fixture = loadPage('pages/mall-product/index.js', {
    getProduct() { return Promise.resolve(richProduct) }
  })
  try {
    fixture.page.onLoad({ id: '43' })
    await flush()
    const html = fixture.page.data.descriptionHtml
    assert.match(html, /src="https:\/\/image\.example\.test\/detail\.jpg"/)
    assert.doesNotMatch(html, /\swidth="1500"/)
    assert.doesNotMatch(html, /\sheight="2000"/)
    assert.match(html, /border-radius:\s*8px/)
    assert.match(html, /display:\s*block/)
    assert.match(html, /width:\s*100%/)
    assert.match(html, /max-width:\s*100%/)
    assert.match(html, /height:\s*auto/)
  } finally { fixture.restore() }
})

test('catalog UI follows the two-column reference hierarchy without a combined tab', () => {
  const root = path.resolve(__dirname, '../../pages')
  const catalog = fs.readFileSync(path.join(root, 'mall/index.wxml'), 'utf8')
  const detail = fs.readFileSync(path.join(root, 'mall-product/index.wxml'), 'utf8')
  const app = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../app.json'), 'utf8'))
  assert.doesNotMatch(catalog, /综合/)
  assert.match(catalog, /價格|价格/)
  assert.match(catalog, /分类/)
  assert.match(catalog, /wx:for="\{\{products\}\}"/)
  assert.match(detail, /库存/)
  assert.ok(app.pages.includes('pages/mall-product/index'))
})

test('catalog card retries single-spec add with the same key and routes multi-spec items to details', async (t) => {
  const checkout = require('../../services/mall-checkout-service')
  const intent = require('../../services/mall-intent-service')
  const session = require('../../services/session-service')
  let pending = null
  const addCalls = []
  t.mock.method(session, 'getAccessToken', () => 'test-token')
  t.mock.method(intent, 'getPendingIntent', () => pending)
  t.mock.method(intent, 'savePendingIntent', (value) => (pending = { ...value, idempotencyKey: 'test-cart-retry-key' }))
  t.mock.method(intent, 'clearPendingIntent', () => { pending = null })
  t.mock.method(checkout, 'addToCart', async (...args) => {
    addCalls.push(args)
    if (addCalls.length === 1) throw new Error('请求超时')
  })
  const single = { ...firstProduct, id: '42', skus: [{ ...firstProduct.skus[0], marketPriceCent: 800 }] }
  const fixture = loadPage('pages/mall/index.js', {
    listCategories: async () => categories,
    listProducts: async () => ({ items: [single, firstProduct] })
  })
  try {
    await fixture.page.onLoad()
    assert.equal(fixture.page.data.products[0].marketPriceText, '8.00')
    const tap = (id) => fixture.page.addCardProduct({ currentTarget: { dataset: { id } } })
    await Promise.all([tap('42'), tap('42')])
    assert.equal(addCalls.length, 1)
    await tap('42')
    assert.deepEqual(addCalls, [['101', 1, 'test-cart-retry-key'], ['101', 1, 'test-cart-retry-key']])
    assert.equal(pending, null)
    await tap('41')
    assert.deepEqual(fixture.navigations, ['/pages/mall-product/index?id=41'])
  } finally { fixture.restore() }
})

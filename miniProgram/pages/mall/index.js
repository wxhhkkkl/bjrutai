const mallCheckoutService = require('../../services/mall-checkout-service')
const mallIntentService = require('../../services/mall-intent-service')
const sessionService = require('../../services/session-service')
const mallCatalogService = require('../../services/mall-catalog-service')
const { updateTabBar } = require('../../services/navigation-service')

const PAGE_SIZE = 20

function formatPrice(priceCent) {
  if (!Number.isSafeInteger(priceCent) || priceCent < 0) return '--'
  return (priceCent / 100).toFixed(2)
}

function mapProduct(product, categories) {
  const skus = Array.isArray(product.skus) ? product.skus : []
  const lowestPriceSku = skus.reduce((lowest, sku) => {
    if (!Number.isSafeInteger(sku.priceCent) || sku.priceCent < 0) return lowest
    return !lowest || sku.priceCent < lowest.priceCent ? sku : lowest
  }, null)
  const category = categories.find((item) => item.id === product.categoryId)
  const availability = mallCatalogService.productAvailability(product)
  const marketPriceCent = lowestPriceSku && lowestPriceSku.marketPriceCent
  const marketPriceText = Number.isSafeInteger(marketPriceCent) && marketPriceCent >= 0
    ? formatPrice(marketPriceCent)
    : ''

  return {
    ...product,
    priceText: lowestPriceSku ? formatPrice(lowestPriceSku.priceCent) : '--',
    marketPriceText,
    availability,
    availabilityText: availability === 'available' ? '' : '暂时售罄',
    categoryName: category ? category.name : ''
  }
}

function safeErrorMessage(error, fallback) {
  const message = error && typeof error.message === 'string' ? error.message.trim() : ''
  return message || fallback
}

Page({
  requestVersion: 0,
  openingProductId: '',

  data: {
    state: 'loading',
    stateMessage: '',
    products: [],
    categoryOptions: [{ id: '', name: '全部分类' }],
    selectedCategoryId: '',
    selectedCategoryName: '分类',
    categoryFilterVisible: false,
    refreshing: false,
    searchText: '',
    sortMode: 'default',
    nextCursor: '',
    hasMore: false,
    loadingMore: false,
    loadMoreError: '',
    addingProductId: '',
    cartFlights: []
  },

  onLoad() {
    this.requestVersion = 0
    this.openingProductId = ''
    return this.loadCatalog(true)
  },

  onShow() {
    updateTabBar(this, 'mall')
    this.openingProductId = ''
  },

  onUnload() {
    this.requestVersion += 1
    this.cartFlyVersion = (this.cartFlyVersion || 0) + 1
    if (this.cartFlyTimer) clearTimeout(this.cartFlyTimer)
  },

  onPullDownRefresh() {
    return this.refreshCatalog()
  },

  onRefresherRefresh() {
    return this.refreshCatalog()
  },

  refreshCatalog() {
    this.setData({ refreshing: true })
    return this.loadCatalog(true).finally(() => this.setData({ refreshing: false }))
  },

  onReachBottom() {
    this.loadCatalog(false)
  },

  async loadCatalog(reset) {
    const shouldReset = reset !== false
    if (!shouldReset && (this.data.state !== 'success' || !this.data.hasMore || this.data.loadingMore)) return

    const version = shouldReset ? ++this.requestVersion : this.requestVersion
    const options = {
      pageSize: PAGE_SIZE,
      sort: this.data.sortMode
    }
    if (this.data.selectedCategoryId) options.categoryId = this.data.selectedCategoryId
    if (this.data.searchText.trim()) options.q = this.data.searchText.trim()
    if (!shouldReset && this.data.nextCursor) options.cursor = this.data.nextCursor

    this.setData(shouldReset
      ? {
          state: 'loading',
          stateMessage: '',
          products: [],
          nextCursor: '',
          hasMore: false,
          loadingMore: false,
          loadMoreError: ''
        }
      : { loadingMore: true, loadMoreError: '' })

    const categoryRequest = shouldReset
      ? mallCatalogService.listCategories({ pageSize: 100 }).catch(() => null)
      : Promise.resolve(null)

    try {
      const [categoryPage, productPage] = await Promise.all([
        categoryRequest,
        mallCatalogService.listProducts(options)
      ])
      if (version !== this.requestVersion) return

      const categories = categoryPage && Array.isArray(categoryPage.items)
        ? categoryPage.items.filter((item) => item && item.status !== 'disabled')
        : null
      const categoryOptions = categories
        ? [{ id: '', name: '全部分类' }].concat(categories.map((item) => ({ id: String(item.id), name: item.name })))
        : this.data.categoryOptions
      const items = productPage && Array.isArray(productPage.items) ? productPage.items : null
      if (!items) throw new Error('商品列表数据格式异常，请重试')

      const products = items.map((item) => mapProduct(item, categoryOptions))
      const combined = shouldReset ? products : this.data.products.concat(products)
      const view = mallCatalogService.catalogViewState({ items: combined })
      this.setData({
        state: view,
        stateMessage: view === 'empty' ? '暂时没有找到符合条件的商品' : '',
        products: combined,
        categoryOptions,
        nextCursor: productPage.nextCursor || '',
        hasMore: Boolean(productPage.nextCursor),
        loadingMore: false,
        loadMoreError: ''
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      if (!shouldReset) {
        this.setData({
          loadingMore: false,
          loadMoreError: safeErrorMessage(error, '加载更多商品失败，请重试')
        })
        return
      }
      const state = mallCatalogService.catalogViewState(null, error)
      this.setData({
        state,
        stateMessage: state === 'forbidden'
          ? '当前账号暂不可访问商城'
          : safeErrorMessage(error, '商品加载失败，请稍后重试'),
        loadingMore: false,
        loadMoreError: ''
      })
    }
  },

  retry() {
    return this.loadCatalog(true)
  },

  onSearchInput(event) {
    const value = event && event.detail ? event.detail.value : ''
    this.setData({ searchText: typeof value === 'string' ? value : '' })
  },

  submitSearch() {
    return this.loadCatalog(true)
  },

  clearSearch() {
    this.setData({ searchText: '' })
    return this.loadCatalog(true)
  },

  togglePriceSort() {
    const sortMode = this.data.sortMode === 'price_asc' ? 'price_desc' : 'price_asc'
    this.setData({ sortMode })
    return this.loadCatalog(true)
  },

  openCategoryFilter() {
    this.setData({ categoryFilterVisible: true })
  },

  closeCategoryFilter() {
    this.setData({ categoryFilterVisible: false })
  },

  stopPropagation() {},

  selectCategory(event) {
    const dataset = event && event.currentTarget ? event.currentTarget.dataset || {} : {}
    const id = dataset.id === undefined ? '' : String(dataset.id)
    const selected = this.data.categoryOptions.find((item) => item.id === id)
    if (!selected) return
    this.setData({
      selectedCategoryId: selected.id,
      selectedCategoryName: selected.id ? selected.name : '分类',
      categoryFilterVisible: false
    })
    return this.loadCatalog(true)
  },

  clearFilters() {
    this.setData({
      searchText: '',
      selectedCategoryId: '',
      selectedCategoryName: '分类',
      sortMode: 'default',
      categoryFilterVisible: false
    })
    return this.loadCatalog(true)
  },

  openProduct(event) {
    const dataset = event && event.currentTarget ? event.currentTarget.dataset || {} : {}
    const productId = String(dataset.id || '')
    if (!/^[1-9][0-9]*$/.test(productId) || this.openingProductId === productId) return
    this.openingProductId = productId
    wx.navigateTo({
      url: `/pages/mall-product/index?id=${encodeURIComponent(productId)}`,
      complete: () => { this.openingProductId = '' }
    })
  },

  animateCartFly(source, target, version) {
    if (!source || !target || version !== this.cartFlyVersion) return

    const flight = {
      id: version,
      left: source.left,
      top: source.top,
      size: source.width,
      deltaX: target.left + (target.width - source.width) / 2 - source.left,
      deltaY: target.top + (target.height - source.height) / 2 - source.top
    }

    // A new key starts a fresh CSS animation even if a previous flight is visible.
    this.setData({ cartFlights: [flight] }, () => {
      if (version !== this.cartFlyVersion) return
      this.cartFlyTimer = setTimeout(() => {
        if (version === this.cartFlyVersion) this.setData({ cartFlights: [] })
      }, 460)
    })
  },

  playCartFly(productId) {
    const version = (this.cartFlyVersion || 0) + 1
    this.cartFlyVersion = version
    if (this.cartFlyTimer) clearTimeout(this.cartFlyTimer)
    if (this.data.cartFlights.length) this.setData({ cartFlights: [] })

    const cart = this.selectComponent?.('#mall-floating-cart')
    if (!cart || typeof cart.getIconRect !== 'function') return
    const query = wx.createSelectorQuery().in(this)
    query.select(`#mall-product-add-${productId}`).boundingClientRect()
    query.exec((rects) => {
      const source = rects && rects[0]
      if (!source || version !== this.cartFlyVersion) return
      cart.getIconRect((target) => this.animateCartFly(source, target, version))
    })
  },

  async addCardProduct(event) {
    if (this.data.addingProductId) return
    const productId = String(event.currentTarget.dataset.id)
    const product = this.data.products.find((item) => String(item.id) === productId)
    if (!product || product.availability !== 'available') return
    if (product.skus.length !== 1) return this.openProduct(event)

    const skuId = String(product.skus[0].id)
    this.setData({ addingProductId: productId })
    try {
      let intent = mallIntentService.getPendingIntent()
      if (!intent || intent.action !== 'add_to_cart' || intent.skuId !== skuId || intent.quantity !== 1) {
        intent = mallIntentService.savePendingIntent({ action: 'add_to_cart', skuId, quantity: 1 })
      }
      if (!sessionService.getAccessToken()) {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
        return
      }
      await mallCheckoutService.addToCart(skuId, 1, intent.idempotencyKey)
      mallIntentService.clearPendingIntent()
      this.playCartFly(productId)
      this.selectComponent?.('#mall-floating-cart')?.refresh()
      wx.showToast({ title: '已加入购物车', icon: 'success' })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      } else {
        wx.showToast({ title: safeErrorMessage(error, '加购失败，请重试'), icon: 'none' })
      }
    } finally {
      this.setData({ addingProductId: '' })
    }
  }
})

const mallCatalogService = require('../../services/mall-catalog-service')
const { updateTabBar } = require('../../services/navigation-service')

const PAGE_SIZE = 20

function formatPrice(priceCent) {
  if (!Number.isSafeInteger(priceCent) || priceCent < 0) return '--'
  return (priceCent / 100).toFixed(2)
}

function mapProduct(product, categories) {
  const skus = Array.isArray(product.skus) ? product.skus : []
  const prices = skus.map((sku) => sku.priceCent).filter((value) => Number.isSafeInteger(value) && value >= 0)
  const category = categories.find((item) => item.id === product.categoryId)
  const availability = mallCatalogService.productAvailability(product)

  return {
    ...product,
    priceText: prices.length ? formatPrice(Math.min(...prices)) : '--',
    availability,
    availabilityText: availability === 'available' ? '有库存' : '暂时售罄',
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
    loadMoreError: ''
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

  openCart() {
    wx.navigateTo({ url: '/pages/mall-cart/index' })
  }
})

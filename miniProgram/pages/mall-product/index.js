const mallCatalogService = require('../../services/mall-catalog-service')
const mallCheckoutService = require('../../services/mall-checkout-service')
const mallIntentService = require('../../services/mall-intent-service')
const sessionService = require('../../services/session-service')

function formatPrice(priceCent) {
  if (!Number.isSafeInteger(priceCent) || priceCent < 0) return '--'
  return (priceCent / 100).toFixed(2)
}

function stockText(quantity) {
  return Number.isSafeInteger(quantity) && quantity > 0 ? `库存 ${quantity} 件` : '有库存'
}

function mapSku(sku) {
  const values = Array.isArray(sku.options)
    ? sku.options.map((option) => option && option.value).filter(Boolean)
    : []
  const availability = sku.stockStatus === 'available' ? 'available' : 'sold_out'
  const marketPriceText = Number.isSafeInteger(sku.marketPriceCent) && sku.marketPriceCent >= 0
    ? formatPrice(sku.marketPriceCent)
    : ''
  return {
    ...sku,
    label: values.length ? values.join(' / ') : '默认规格',
    priceText: formatPrice(sku.priceCent),
    marketPriceText,
    availability,
    availabilityText: availability === 'available' ? stockText(sku.availableQuantity) : '暂时售罄'
  }
}

Page({
  requestVersion: 0,

  data: {
    state: 'loading',
    stateMessage: '',
    product: null,
    images: [],
    skus: [],
    selectedSkuId: '',
    selectedSku: null,
    priceText: '--',
    marketPriceText: '',
    availability: 'sold_out',
    availabilityText: '暂时售罄',
    purchaseBusy: false,
    purchaseMessage: ''
  },

  onLoad(options = {}) {
    this.productId = typeof options.id === 'string' ? options.id : ''
    this.requestVersion = 0
    return this.loadProduct()
  },

  onUnload() {
    this.requestVersion += 1
  },

  async loadProduct() {
    const version = ++this.requestVersion
    if (!/^[1-9][0-9]*$/.test(this.productId || '')) {
      this.setData({ state: 'empty', stateMessage: '商品编号不正确，请返回商城重新选择' })
      return
    }
    this.setData({ state: 'loading', stateMessage: '' })
    try {
      const product = await mallCatalogService.getProduct(this.productId)
      if (version !== this.requestVersion) return
      if (!product || product.status !== 'on_sale') {
        this.setData({ state: 'empty', stateMessage: '商品已下架或不存在' })
        return
      }

      const skus = Array.isArray(product.skus) ? product.skus.map(mapSku) : []
      const selectedSku = skus.find((item) => item.availability === 'available') || skus[0] || null
      const imageUrls = []
      if (product.coverUrl) imageUrls.push(product.coverUrl)
      if (Array.isArray(product.galleryUrls)) {
        product.galleryUrls.forEach((url) => {
          if (url && !imageUrls.includes(url)) imageUrls.push(url)
        })
      }
      const prices = skus.map((sku) => sku.priceCent).filter((value) => Number.isSafeInteger(value) && value >= 0)
      const availability = selectedSku
        ? selectedSku.availability
        : mallCatalogService.productAvailability(product)
      this.setData({
        state: 'success',
        stateMessage: '',
        product,
        descriptionHtml: typeof product.description === 'string' && product.description.startsWith('<!--mall-rich-text-->')
          ? product.description.slice('<!--mall-rich-text-->'.length)
          : '',
        images: imageUrls,
        skus,
        selectedSkuId: selectedSku ? selectedSku.id : '',
        selectedSku,
        priceText: selectedSku ? selectedSku.priceText : (prices.length ? formatPrice(Math.min(...prices)) : '--'),
        marketPriceText: selectedSku ? selectedSku.marketPriceText : '',
        availability,
        availabilityText: selectedSku
          ? selectedSku.availabilityText
          : (availability === 'available' ? '有库存' : '暂时售罄')
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      const status = Number(error && (error.httpStatus || error.statusCode))
      const state = status === 403 ? 'forbidden' : status === 404 ? 'empty' : 'recoverable-error'
      const stateMessage = status === 403
        ? '当前账号暂不可访问该商品'
        : status === 404
          ? '商品已下架或不存在'
          : (error && error.message) || '商品详情加载失败，请稍后重试'
      this.setData({ state, stateMessage })
    }
  },

  retry() {
    return this.loadProduct()
  },

  selectSku(event) {
    const dataset = event && event.currentTarget ? event.currentTarget.dataset || {} : {}
    const selectedSku = this.data.skus.find((item) => item.id === String(dataset.id || ''))
    if (!selectedSku) return
    this.setData({
      selectedSkuId: selectedSku.id,
      selectedSku,
      priceText: selectedSku.priceText,
      marketPriceText: selectedSku.marketPriceText,
      availability: selectedSku.availability,
      availabilityText: selectedSku.availabilityText
    })
  },

  goBack() {
    wx.navigateBack({ delta: 1 })
  },

  async addToCart() {
    return this.applyPurchaseIntent('add_to_cart')
  },

  async buyNow() {
    return this.applyPurchaseIntent('buy_now')
  },

  async applyPurchaseIntent(action) {
    const sku = this.data.selectedSku
    if (!sku || sku.availability !== 'available') {
      wx.showToast({ title: '该规格暂时无库存', icon: 'none' })
      return
    }
    if (this.data.purchaseBusy) return
    const quantity = 1
    const intent = {
      action,
      skuId: String(sku.id),
      quantity,
      deliveryMethod: this.data.product.deliveryMethod === 'virtual' || this.data.product.productType === 'virtual' ? 'virtual' : 'express'
    }
    if (!sessionService.getAccessToken()) {
      mallIntentService.savePendingIntent(intent)
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      return
    }
    if (action === 'buy_now') {
      mallIntentService.saveCheckoutDraft({
        items: [{ skuId: String(sku.id), quantity }],
        deliveryMethod: intent.deliveryMethod,
        source: 'buy_now'
      })
      mallIntentService.clearPendingIntent()
      wx.navigateTo({ url: '/pages/mall-checkout/index' })
      return
    }

    let pending = mallIntentService.getPendingIntent()
    if (!pending || pending.action !== action || pending.skuId !== String(sku.id) || pending.quantity !== quantity) {
      pending = mallIntentService.savePendingIntent(intent)
    }
    this.setData({ purchaseBusy: true, purchaseMessage: '' })
    try {
      await mallCheckoutService.addToCart(pending.skuId, pending.quantity, pending.idempotencyKey)
      mallIntentService.clearPendingIntent()
      this.selectComponent?.('#mall-floating-cart')?.refresh()
      wx.showToast({ title: '已加入购物车', icon: 'success' })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      } else {
        this.setData({ purchaseMessage: (error && error.message) || '加入结果待确认，再次操作会复用原请求凭证' })
      }
    } finally {
      this.setData({ purchaseBusy: false })
    }
  },

  backToMall() {
    wx.switchTab({ url: '/pages/mall/index' })
  }
})

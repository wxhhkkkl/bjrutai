const mallService = require('../../services/mall-checkout-service')
const mallIntent = require('../../services/mall-intent-service')
const sessionService = require('../../services/session-service')
const { createRequestKeyManager } = require('../../utils/request-key')

const CART_REMOVE_ANIMATION_MS = 220

function money(value) {
  return Number.isSafeInteger(value) && value >= 0 ? (value / 100).toFixed(2) : '--'
}

function key() {
  return mallIntent.createIdempotencyKey()
}

function selectedTotal(items, selectedIds) {
  const selected = new Set(selectedIds)
  return (items || []).reduce((total, item) => {
    if (!item.valid || !selected.has(item.id)) return total
    return total + (Number(item.sku && item.sku.priceCent) || 0) * item.quantity
  }, 0)
}

Page({
  data: {
    state: 'loading',
    stateMessage: '',
    items: [],
    openDeleteId: '',
    removingId: '',
    removingHeight: 0,
    removingCollapsed: false,
    selectedIds: [],
    selectedCount: 0,
    allSelected: false,
    totalText: '0.00',
    busyId: '',
    purchaseAvailable: false
  },

  onLoad() {
    return this.ensureBuyerAndLoad()
  },

  onShow() {
    if (sessionService.getAccessToken()) this.ensureBuyerAndLoad()
  },

  async ensureBuyerAndLoad() {
    if (!sessionService.getAccessToken()) {
      wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
      return
    }
    const pending = mallIntent.getPendingIntent()
    if (pending && pending.action === 'add_to_cart') {
      try {
        await mallService.addToCart(pending.skuId, pending.quantity, pending.idempotencyKey)
        mallIntent.clearPendingIntent()
        wx.showToast({ title: '已加入购物车', icon: 'success' })
      } catch (error) {
        if (error && error.kind === 'AUTH') {
          wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
          return
        }
        this.setData({ stateMessage: (error && error.message) || '商品暂未加入，请重试' })
      }
    }
    return this.loadCart()
  },

  async loadCart() {
    this.setData({ state: 'loading', stateMessage: '', openDeleteId: '', removingId: '', removingHeight: 0, removingCollapsed: false })
    try {
      const [page, settings] = await Promise.all([
        mallService.getCart({ pageSize: 100 }),
        mallService.getCheckoutSettings()
      ])
      const items = Array.isArray(page && page.items) ? page.items.map((item) => ({
        ...item,
        id: String(item.id),
        skuId: String(item.sku && item.sku.id),
        skuLabel: Array.isArray(item.sku && item.sku.options) && item.sku.options.length
          ? item.sku.options.map((option) => option.value).filter(Boolean).join(' / ')
          : '默认规格',
        coverImageFailed: false,
        priceText: money(item.sku && item.sku.priceCent),
        lineText: money((Number(item.sku && item.sku.priceCent) || 0) * item.quantity)
      })) : []
      const selectedIds = items.filter((item) => item.valid).map((item) => item.id)
      const selected = new Set(selectedIds)
      const displayItems = items.map((item) => ({ ...item, selected: selected.has(item.id) }))
      this.setData({
        state: items.length ? 'success' : 'empty',
        items: displayItems,
        selectedIds,
        selectedCount: selectedIds.length,
        allSelected: selectedIds.length > 0 && selectedIds.length === items.filter((item) => item.valid).length,
        totalText: money(selectedTotal(items, selectedIds)),
        purchaseAvailable: Boolean(settings && settings.purchasingAvailable)
      })
    } catch (error) {
      if (error && error.kind === 'AUTH') {
        wx.navigateTo({ url: '/pages/auth/login/index?from=mall' })
        return
      }
      this.setData({ state: 'recoverable-error', stateMessage: (error && error.message) || '购物车加载失败，请重试' })
    }
  },

  retry() {
    return this.ensureBuyerAndLoad()
  },

  onCartImageError(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    if (!id) return
    this.setData({
      items: this.data.items.map((item) => (
        item.id === id ? { ...item, coverImageFailed: true } : item
      ))
    })
  },

  toggleItem(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    const item = this.data.items.find((row) => row.id === id)
    if (!item || !item.valid) return
    const selected = new Set(this.data.selectedIds)
    if (selected.has(id)) selected.delete(id)
    else selected.add(id)
    const selectedIds = Array.from(selected)
    const displayItems = this.data.items.map((row) => ({ ...row, selected: selected.has(row.id) }))
    const validCount = displayItems.filter((row) => row.valid).length
    this.setData({ selectedIds, selectedCount: selectedIds.length, allSelected: selectedIds.length > 0 && selectedIds.length === validCount, items: displayItems, totalText: money(selectedTotal(displayItems, selectedIds)) })
  },

  toggleAll() {
    const validIds = this.data.items.filter((item) => item.valid).map((item) => item.id)
    const selectedIds = validIds.length === this.data.selectedIds.length ? [] : validIds
    const selected = new Set(selectedIds)
    const items = this.data.items.map((item) => ({ ...item, selected: selected.has(item.id) }))
    this.setData({ selectedIds, selectedCount: selectedIds.length, allSelected: selectedIds.length > 0 && selectedIds.length === validIds.length, items, totalText: money(selectedTotal(items, selectedIds)) })
  },

  onCartTouchStart(event) {
    const touch = event && event.touches && event.touches[0]
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    if (!touch || !id) return
    this.cartSwipeTouch = {
      id,
      startX: Number(touch.clientX),
      startY: Number(touch.clientY)
    }
  },

  onCartTouchEnd(event) {
    const start = this.cartSwipeTouch
    this.cartSwipeTouch = null
    if (!start) return
    const touch = event && ((event.changedTouches && event.changedTouches[0]) || (event.touches && event.touches[0]))
    if (!touch) return
    const deltaX = Number(touch.clientX) - start.startX
    const deltaY = Number(touch.clientY) - start.startY
    const horizontalSwipe = Math.abs(deltaX) >= 40 && Math.abs(deltaX) > Math.abs(deltaY)
    const openDeleteId = this.data.openDeleteId
    const item = this.data.items.find((row) => row.id === start.id)

    if (!horizontalSwipe) {
      if (openDeleteId && Math.abs(deltaX) < 10 && Math.abs(deltaY) < 10) {
        this.setData({ openDeleteId: '' })
      }
      return
    }

    if (!item || !item.valid) {
      if (openDeleteId) this.setData({ openDeleteId: '' })
      return
    }

    this.setData({ openDeleteId: deltaX < 0 ? start.id : '' })
  },

  onCartTouchCancel() {
    this.cartSwipeTouch = null
  },

  async changeQuantity(event) {
    const dataset = event && event.currentTarget ? event.currentTarget.dataset || {} : {}
    const item = this.data.items.find((row) => row.id === String(dataset.id || ''))
    if (!item || !item.valid || this.data.busyId) return
    const delta = dataset.delta === 'down' ? -1 : 1
    const quantity = item.quantity + delta
    if (quantity < 0 || quantity > 999) return
    if (quantity === 0) {
      return this.removeCartItem(item)
    }
    const flowId = `mall-cart-quantity:${item.id}:${item.version}:${quantity}`
    const operationKey = this.keyManager || (this.keyManager = createRequestKeyManager())
    const requestKey = operationKey.begin(flowId)
    this.setData({ busyId: item.id, openDeleteId: '' })
    try {
      await mallService.updateCartItem(item.id, quantity, item.version, requestKey)
      operationKey.markSucceeded(flowId)
      await this.loadCart()
    } catch (error) {
      operationKey.markUnknown(flowId)
      this.setData({ stateMessage: (error && error.message) || '数量更新未确认，请刷新购物车' })
    } finally {
      this.setData({ busyId: '' })
    }
  },

  async removeItem(event) {
    const id = String(event && event.currentTarget && event.currentTarget.dataset.id || '')
    const item = this.data.items.find((row) => row.id === id)
    if (!item || this.data.busyId) return
    return this.removeCartItem(item)
  },

  animateCartRemoval(id) {
    return new Promise((resolve) => {
      if (!id || typeof wx === 'undefined' || typeof wx.createSelectorQuery !== 'function') {
        resolve()
        return
      }
      wx.createSelectorQuery().in(this).select(`#mall-cart-row-${id}`).boundingClientRect((rect) => {
        if (!rect || !(rect.height > 0)) {
          resolve()
          return
        }
        this.setData({ removingId: id, removingHeight: rect.height }, () => {
          this.setData({ removingCollapsed: true })
          setTimeout(resolve, CART_REMOVE_ANIMATION_MS + 20)
        })
      }).exec()
    })
  },

  async removeCartItem(item) {
    if (!item || this.data.busyId) return
    const id = item.id
    const flowId = `mall-cart-remove:${item.id}:${item.version}`
    const operationKey = this.keyManager || (this.keyManager = createRequestKeyManager())
    const requestKey = operationKey.begin(flowId)
    this.setData({ busyId: id, openDeleteId: '' })
    try {
      await mallService.removeCartItem(item.id, item.version, requestKey)
      operationKey.markSucceeded(flowId)
      await this.animateCartRemoval(id)
      await this.loadCart()
    } catch (error) {
      operationKey.markUnknown(flowId)
      this.setData({ stateMessage: (error && error.message) || '移除结果未确认，请刷新购物车' })
    } finally {
      this.setData({ busyId: '' })
    }
  },

  continueCheckout() {
    const selected = new Set(this.data.selectedIds)
    const items = this.data.items.filter((item) => item.valid && selected.has(item.id))
    if (!items.length) {
      wx.showToast({ title: '请先选择有效商品', icon: 'none' })
      return
    }
    if (!this.data.purchaseAvailable) {
      wx.showToast({ title: '商城暂未开放购买', icon: 'none' })
      return
    }
    const deliveryMethods = new Set(items.map((item) => (
      item.deliveryMethod === 'virtual' || item.productType === 'virtual' ? 'virtual' : 'express'
    )))
    if (deliveryMethods.size > 1) {
      wx.showToast({ title: '虚拟商品与实物商品请分开结算', icon: 'none' })
      return
    }
    mallIntent.saveCheckoutDraft({
      items: items.map((item) => ({ skuId: item.skuId, quantity: item.quantity })),
      deliveryMethod: deliveryMethods.has('virtual') ? 'virtual' : 'express',
      source: 'cart'
    })
    wx.navigateTo({ url: '/pages/mall-checkout/index' })
  },

  openAddresses() {
    wx.navigateTo({ url: '/pages/mall-address/index' })
  },

  goBack() {
    wx.navigateBack({ delta: 1 })
  }
})

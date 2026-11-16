const { getCart } = require('../../services/mall-checkout-service')
const { getAccessToken } = require('../../services/session-service')

Component({
  properties: {
    aboveTabBar: Boolean
  },
  data: { quantity: 0 },
  lifetimes: {
    attached() { this.refresh() },
    detached() { this.requestVersion += 1 }
  },
  pageLifetimes: {
    show() { this.refresh() }
  },
  methods: {
    getIconRect(callback) {
      const query = this.createSelectorQuery()
      query.select('.floating-cart__icon').boundingClientRect()
      query.exec((rects) => {
        if (typeof callback === 'function') callback(rects && rects[0])
      })
    },
    async refresh() {
      const version = (this.requestVersion || 0) + 1
      this.requestVersion = version
      const token = getAccessToken()
      if (!token) {
        this.setData({ quantity: 0 })
        return
      }

      let quantity = 0
      let cursor
      try {
        do {
          const page = await getCart({ pageSize: 100, cursor })
          if (version !== this.requestVersion || token !== getAccessToken()) return
          for (const item of page.items) {
            if (Number.isSafeInteger(item.quantity) && item.quantity > 0) quantity += item.quantity
          }
          cursor = page.nextCursor
        } while (cursor)
        this.setData({ quantity })
      } catch (_) {
        if (version === this.requestVersion) this.setData({ quantity: 0 })
      }
    },
    openCart() {
      wx.navigateTo({ url: '/pages/mall-cart/index' })
    }
  }
})

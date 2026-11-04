const { updateTabBar } = require('../../services/navigation-service')

Page({
  data: {
    imageFailed: false
  },

  onShow() {
    updateTabBar(this, 'internet-hospital')
  },

  onImageError() {
    this.setData({ imageFailed: true })
  }
})

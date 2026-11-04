const { updateTabBar } = require('../../services/navigation-service')

Page({
  data: {
    sideCategories: [
      { id: 'recommend', name: '为你推荐', active: true },
      { id: 'heart', name: '心脑维养' },
      { id: 'women', name: '女性健康' },
      { id: 'home', name: '居家健康' },
      { id: 'reading', name: '健康读物' }
    ],
    products: [
      {
        id: 'monitor',
        name: '家用电子血压计',
        category: '居家健康',
        description: '外观与样式示意',
        visual: 'monitor'
      },
      {
        id: 'guidebook',
        name: '家庭健康管理手册',
        category: '健康读物',
        description: '健康科普读物示意',
        visual: 'book'
      },
      {
        id: 'warm-pouch',
        name: '可重复使用热敷袋',
        category: '居家健康',
        description: '日常照护用品示意',
        visual: 'pouch'
      },
      {
        id: 'women-care',
        name: '女性日常护理套装',
        category: '女性健康',
        description: '女性专区商品示意',
        visual: 'care'
      }
    ]
  },

  onShow() {
    updateTabBar(this, 'mall')
  }
})

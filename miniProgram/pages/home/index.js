const { getCurrentSession, getEntry } = require('../../services/session-service')
const articleService = require('../../services/article-service')
const bannerService = require('../../services/banner-service')
const shareConfigService = require('../../services/share-config-service')
const { normalizeArticleId, adaptArticlePage, adaptArticleCategories } = require('../../models/article')
const { adaptBannerList } = require('../../models/banner')
const { openAction, updateTabBar } = require('../../services/navigation-service')
const { resumePendingBinding } = require('../../services/pending-binding-service')

const HOME_SHARE_TITLE = '儒泰医联｜让健康知识，走进日常'
const DEFAULT_HOME_CATEGORIES = {
  about: { id: '', name: '关于儒泰' },
  wellness: { id: '', name: '心脑维养' },
  women: { id: '', name: '女性专区' },
  articles: { id: '', name: '健康资讯' },
}

Page({
  articleRequestVersion: 0,
  bannerRequestVersion: 0,
  homeCategoryRequestVersion: 0,
  aboutRequestVersion: 0,
  wellnessRequestVersion: 0,
  womenRequestVersion: 0,

  data: {
    session: {},
    homeCategories: DEFAULT_HOME_CATEGORIES,
    articleState: 'loading',
    articleStateMessage: '',
    articleItems: [],
    openingArticleId: '',
    aboutState: 'loading',
    aboutLead: null,
    aboutSupportingItems: [],
    wellnessState: 'loading',
    wellnessLead: null,
    wellnessSupportingItems: [],
    womenState: 'loading',
    womenLead: null,
    womenSupportingItems: [],
    bannerState: 'loading',
    bannerItems: [],
    openingBannerId: ''
  },

  onLoad() {
    wx.showShareMenu({ menus: ['shareAppMessage', 'shareTimeline'] })
  },

  onShareAppMessage() {
    const config = shareConfigService.getCachedShareConfig('home')
    return {
      title: config && config.friendTitle || HOME_SHARE_TITLE,
      path: config && config.landingPath || '/pages/home/index',
      imageUrl: config && config.friendImageUrl || '/assets/images/home-share-friend-v1.jpg'
    }
  },

  onShareTimeline() {
    const config = shareConfigService.getCachedShareConfig('home')
    return {
      title: config && config.timelineTitle || HOME_SHARE_TITLE,
      query: '',
      imageUrl: config && config.timelineImageUrl || '/assets/images/home-share-timeline-v1.jpg'
    }
  },

  onShow() {
    const session = getCurrentSession()
    const entry = getEntry(session)

    if (entry.type === 'reLaunch') {
      wx.reLaunch({ url: entry.url })
      return
    }

    shareConfigService.loadShareConfig('home')
    updateTabBar(this, 'home')
    this.setData({ session })
    resumePendingBinding()
    if (this.data.openingArticleId || this.data.openingBannerId) {
      this.setData({ openingArticleId: '', openingBannerId: '' })
    }
    this.loadHomeCategories()
    this.loadBanners()
  },

  onHide() {
    this.articleRequestVersion += 1
    this.bannerRequestVersion += 1
    this.homeCategoryRequestVersion += 1
    this.aboutRequestVersion += 1
    this.wellnessRequestVersion += 1
    this.womenRequestVersion += 1
  },

  onUnload() {
    this.articleRequestVersion += 1
    this.bannerRequestVersion += 1
    this.homeCategoryRequestVersion += 1
    this.aboutRequestVersion += 1
    this.wellnessRequestVersion += 1
    this.womenRequestVersion += 1
  },

  async loadHomeCategories() {
    const version = ++this.homeCategoryRequestVersion
    const homeCategories = Object.assign({}, DEFAULT_HOME_CATEGORIES)

    try {
      const payload = await articleService.listArticleCategories()
      if (version !== this.homeCategoryRequestVersion) return
      const categories = adaptArticleCategories(payload)
      categories.forEach((category) => {
        if (Object.prototype.hasOwnProperty.call(homeCategories, category.homeSectionKey)) {
          homeCategories[category.homeSectionKey] = { id: category.id, name: category.name }
        }
      })
    } catch (error) {
      console.warn('[home] load category names failed; use defaults', error)
    }

    if (version !== this.homeCategoryRequestVersion) return
    this.setData({ homeCategories })
    this.loadArticles(homeCategories.articles)
    this.loadAboutArticle(homeCategories.about)
    this.loadWellnessArticle(homeCategories.wellness)
    this.loadWomenArticle(homeCategories.women)
  },

  async loadArticles(category = this.data.homeCategories.articles) {
    const version = ++this.articleRequestVersion
    this.setData({
      articleState: 'loading',
      articleStateMessage: '',
      articleItems: []
    })

    try {
      const payload = await articleService.listArticles(category && category.id
        ? { categoryId: category.id, limit: 20 }
        : { limit: 20 })
      if (version !== this.articleRequestVersion) return
      const page = adaptArticlePage(payload)
      let items = page.items.slice(0, 3)
      if (!category || !category.id) {
        const womenItems = page.items.filter((item) => item.category === this.data.homeCategories.women.name)
        const otherItems = page.items.filter((item) => item.category !== this.data.homeCategories.about.name
          && item.category !== this.data.homeCategories.women.name)
        items = otherItems.concat(womenItems.slice(3)).slice(0, 3)
      }
      this.setData({
        articleState: items.length ? 'success' : 'empty',
        articleStateMessage: items.length ? '' : '暂无已发布文章',
        articleItems: items
      })
    } catch (error) {
      if (version !== this.articleRequestVersion) return
      this.setData({
        articleState: 'recoverable-error',
        articleStateMessage: error && error.message ? error.message : '文章暂时无法加载',
        articleItems: []
      })
    }
  },

  retryArticles() {
    this.loadArticles(this.data.homeCategories.articles)
  },

  async loadAboutArticle(category = this.data.homeCategories.about) {
    const version = ++this.aboutRequestVersion
    this.setData({
      aboutState: 'loading',
      aboutLead: null,
      aboutSupportingItems: []
    })

    try {
      const payload = await articleService.listArticles(category && category.id
        ? { categoryId: category.id, limit: 3 }
        : { category: '关于儒泰', limit: 3 })
      if (version !== this.aboutRequestVersion) return
      const page = adaptArticlePage(payload)
      const items = page.items.slice(0, 3)
      this.setData({
        aboutState: items.length ? 'success' : 'empty',
        aboutLead: items[0] || null,
        aboutSupportingItems: items.slice(1, 3)
      })
    } catch (error) {
      if (version !== this.aboutRequestVersion) return
      this.setData({
        aboutState: 'recoverable-error',
        aboutLead: null,
        aboutSupportingItems: []
      })
    }
  },

  async loadWellnessArticle(category = this.data.homeCategories.wellness) {
    const version = ++this.wellnessRequestVersion
    this.setData({
      wellnessState: 'loading',
      wellnessLead: null,
      wellnessSupportingItems: []
    })

    try {
      const payload = await articleService.listArticles(category && category.id
        ? { categoryId: category.id, limit: 3 }
        : { category: '心脑维养', limit: 3 })
      if (version !== this.wellnessRequestVersion) return
      const page = adaptArticlePage(payload)
      const items = page.items.slice(0, 3)
      this.setData({
        wellnessState: items.length ? 'success' : 'empty',
        wellnessLead: items[0] || null,
        wellnessSupportingItems: items.slice(1, 3)
      })
    } catch (error) {
      if (version !== this.wellnessRequestVersion) return
      this.setData({
        wellnessState: 'recoverable-error',
        wellnessLead: null,
        wellnessSupportingItems: []
      })
    }
  },

  async loadWomenArticle(category = this.data.homeCategories.women) {
    const version = ++this.womenRequestVersion
    this.setData({
      womenState: 'loading',
      womenLead: null,
      womenSupportingItems: []
    })

    try {
      const payload = await articleService.listArticles(category && category.id
        ? { categoryId: category.id, limit: 3 }
        : { category: '女性专区', limit: 3 })
      if (version !== this.womenRequestVersion) return
      const page = adaptArticlePage(payload)
      const items = page.items.slice(0, 3)
      this.setData({
        womenState: items.length ? 'success' : 'empty',
        womenLead: items[0] || null,
        womenSupportingItems: items.slice(1, 3)
      })
    } catch (error) {
      if (version !== this.womenRequestVersion) return
      this.setData({
        womenState: 'recoverable-error',
        womenLead: null,
        womenSupportingItems: []
      })
    }
  },

  async loadBanners() {
    const version = ++this.bannerRequestVersion
    this.setData({ bannerState: 'loading', bannerItems: [] })

    try {
      const payload = await bannerService.listBanners()
      if (version !== this.bannerRequestVersion) return
      const items = adaptBannerList(payload)
      this.setData({
        bannerState: items.length ? 'success' : 'empty',
        bannerItems: items
      })
    } catch (error) {
      if (version !== this.bannerRequestVersion) return
      // 轮播图属于可选内容，加载失败不影响首页内容与文章资讯。
      this.setData({ bannerState: 'recoverable-error', bannerItems: [] })
    }
  },

  openBanner(e) {
    if (this.data.openingBannerId) return
    const bannerId = e.currentTarget.dataset.id
    const banner = this.data.bannerItems.find((item) => item.bannerId === bannerId)
    if (!banner || banner.actionType !== 'article') return
    this.setData({ openingBannerId: banner.bannerId })
    wx.navigateTo({
      url: `/pages/article-detail/index?articleId=${encodeURIComponent(banner.articleId)}`,
      fail: () => this.setData({ openingBannerId: '' })
    })
  },

  hideBrokenBanner(e) {
    const bannerId = e.currentTarget.dataset.id
    const bannerItems = this.data.bannerItems.filter((item) => item.bannerId !== bannerId)
    this.setData({
      bannerItems,
      bannerState: bannerItems.length ? 'success' : 'empty'
    })
  },

  onHomeCategoryIconError(e) {
    const iconKey = e.currentTarget.dataset.iconKey
    console.error('[home] category icon failed to load', iconKey, e.detail && e.detail.errMsg)
  },

  openArticle(e) {
    if (this.data.openingArticleId) return
    let articleId
    try {
      articleId = normalizeArticleId(e.currentTarget.dataset.id)
    } catch (error) {
      return
    }
    this.setData({ openingArticleId: articleId })
    wx.navigateTo({
      url: `/pages/article-detail/index?articleId=${encodeURIComponent(articleId)}`,
      fail: () => this.setData({ openingArticleId: '' })
    })
  },

  openArticleCategory(e) {
    const rawCategoryId = e.currentTarget.dataset.categoryId
    let categoryId = ''
    if (rawCategoryId !== undefined && rawCategoryId !== null && String(rawCategoryId).trim()) {
      try {
        categoryId = normalizeArticleId(rawCategoryId)
      } catch (error) {
        // Fall back to the legacy name query when a category ID is unavailable.
      }
    }
    const homeCategory = categoryId
      ? Object.values(this.data.homeCategories || {}).find((item) => item.id === categoryId)
      : null
    const category = homeCategory && homeCategory.name || (typeof e.currentTarget.dataset.category === 'string'
      ? e.currentTarget.dataset.category.trim()
      : '')
    if (!category) return

    const query = categoryId
      ? `categoryId=${encodeURIComponent(categoryId)}`
      : `category=${encodeURIComponent(category)}`
    wx.navigateTo({
      url: `/pages/articles/index?${query}&categoryName=${encodeURIComponent(category)}`
    })
  },

  action(e) {
    const result = openAction(
      e.currentTarget.dataset.id,
      this.data.session
    )

    if (result.ok) {
      wx.navigateTo({ url: result.url })
    } else {
      wx.showToast({ title: result.message, icon: 'none' })
    }
  }
})

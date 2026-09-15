const { getCurrentSession, getEntry } = require('../../services/session-service')
const articleService = require('../../services/article-service')
const bannerService = require('../../services/banner-service')
const { normalizeArticleId, adaptArticlePage } = require('../../models/article')
const { adaptBannerList } = require('../../models/banner')
const { openAction, updateTabBar } = require('../../services/navigation-service')

Page({
  articleRequestVersion: 0,
  bannerRequestVersion: 0,
  aboutRequestVersion: 0,

  data: {
    session: {},
    articleState: 'loading',
    articleStateMessage: '',
    articleItems: [],
    openingArticleId: '',
    aboutState: 'loading',
    aboutArticle: null,
    bannerState: 'loading',
    bannerItems: [],
    openingBannerId: ''
  },

  onShow() {
    const session = getCurrentSession()
    const entry = getEntry(session)

    if (entry.type === 'reLaunch') {
      wx.reLaunch({ url: entry.url })
      return
    }

    updateTabBar(this, 'home')
    this.setData({ session })
    if (this.data.openingArticleId || this.data.openingBannerId) {
      this.setData({ openingArticleId: '', openingBannerId: '' })
    }
    this.loadArticles()
    this.loadAboutArticle()
    this.loadBanners()
  },

  onHide() {
    this.articleRequestVersion += 1
    this.bannerRequestVersion += 1
    this.aboutRequestVersion += 1
  },

  onUnload() {
    this.articleRequestVersion += 1
    this.bannerRequestVersion += 1
    this.aboutRequestVersion += 1
  },

  async loadArticles() {
    const version = ++this.articleRequestVersion
    this.setData({
      articleState: 'loading',
      articleStateMessage: '',
      articleItems: []
    })

    try {
      const payload = await articleService.listArticles({ limit: 4 })
      if (version !== this.articleRequestVersion) return
      const page = adaptArticlePage(payload)
      const items = page.items.filter((item) => item.category !== '关于儒泰').slice(0, 3)
      this.setData({
        articleState: items.length ? 'success' : 'empty',
        articleStateMessage: items.length ? '' : '暂无已发布文章',
        articleItems: items
      })
    } catch (error) {
      if (version !== this.articleRequestVersion) return
      this.setData({
        articleState: 'recoverable-error',
        articleStateMessage: error && error.message ? error.message : '文章暂时无法加载'
      })
    }
  },

  retryArticles() {
    this.loadArticles()
  },

  async loadAboutArticle() {
    const version = ++this.aboutRequestVersion
    this.setData({ aboutState: 'loading', aboutArticle: null })

    try {
      const payload = await articleService.listArticles({ category: '关于儒泰', limit: 1 })
      if (version !== this.aboutRequestVersion) return
      const page = adaptArticlePage(payload)
      this.setData({
        aboutState: page.items.length ? 'success' : 'empty',
        aboutArticle: page.items[0] || null
      })
    } catch (error) {
      if (version !== this.aboutRequestVersion) return
      this.setData({ aboutState: 'recoverable-error', aboutArticle: null })
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
    const category = typeof e.currentTarget.dataset.category === 'string'
      ? e.currentTarget.dataset.category.trim()
      : ''
    if (!category) return
    wx.navigateTo({
      url: `/pages/articles/index?category=${encodeURIComponent(category)}`
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

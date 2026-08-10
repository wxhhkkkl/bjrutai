const articleService = require('../../services/article-service')
const { normalizeArticleId, adaptArticlePage, mergeArticlePage } = require('../../models/article')

Page({
  requestVersion: 0,

  data: {
    state: 'loading',
    stateMessage: '',
    items: [],
    nextCursor: '',
    hasMore: false,
    loadingMore: false,
    loadMoreError: '',
    openingArticleId: ''
  },

  onLoad() {
    this.loadFirstPage(false)
  },

  onShow() {
    if (this.data.openingArticleId) this.setData({ openingArticleId: '' })
  },

  onUnload() {
    this.requestVersion += 1
  },

  async loadFirstPage(fromRefresh) {
    const version = ++this.requestVersion
    this.setData({
      state: 'loading',
      stateMessage: '',
      items: [],
      nextCursor: '',
      hasMore: false,
      loadingMore: false,
      loadMoreError: ''
    })

    try {
      const payload = await articleService.listArticles({ limit: 20 })
      if (version !== this.requestVersion) return
      const page = adaptArticlePage(payload)
      this.setData({
        state: page.items.length ? 'success' : 'empty',
        stateMessage: page.items.length ? '' : '暂无已发布文章',
        items: page.items,
        nextCursor: page.nextCursor,
        hasMore: page.hasMore
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({
        state: 'recoverable-error',
        stateMessage: error && error.message ? error.message : '文章列表加载失败，请稍后重试'
      })
    } finally {
      if (fromRefresh && typeof wx.stopPullDownRefresh === 'function') wx.stopPullDownRefresh()
    }
  },

  onPullDownRefresh() {
    this.loadFirstPage(true)
  },

  onReachBottom() {
    this.loadMore()
  },

  async loadMore() {
    if (this.data.state !== 'success' || !this.data.hasMore || this.data.loadingMore) return
    const version = this.requestVersion
    const currentCursor = this.data.nextCursor
    this.setData({ loadingMore: true, loadMoreError: '' })

    try {
      const payload = await articleService.listArticles({ limit: 20, cursor: currentCursor })
      if (version !== this.requestVersion) return
      const page = adaptArticlePage(payload)
      const merged = mergeArticlePage(this.data.items, page, currentCursor)
      this.setData({
        items: merged.items,
        nextCursor: merged.nextCursor,
        hasMore: merged.hasMore,
        loadMoreError: merged.paginationError
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({
        loadMoreError: error && error.message ? error.message : '加载更多失败，请重试'
      })
    } finally {
      if (version === this.requestVersion) this.setData({ loadingMore: false })
    }
  },

  retry() {
    this.loadFirstPage(false)
  },

  retryLoadMore() {
    this.loadMore()
  },

  openArticle(event) {
    if (this.data.openingArticleId) return
    let articleId
    try {
      articleId = normalizeArticleId(event.currentTarget.dataset.id)
    } catch (error) {
      return
    }
    this.setData({ openingArticleId: articleId })
    wx.navigateTo({
      url: `/pages/article-detail/index?articleId=${encodeURIComponent(articleId)}`,
      fail: () => this.setData({ openingArticleId: '' })
    })
  },

  handleBack() {
    if (typeof getCurrentPages === 'function' && getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 })
      return
    }
    wx.switchTab({ url: '/pages/home/index' })
  }
})

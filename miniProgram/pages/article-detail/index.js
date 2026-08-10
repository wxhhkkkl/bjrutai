const articleService = require('../../services/article-service')
const { normalizeArticleId, adaptArticleDetail } = require('../../models/article')

Page({
  requestVersion: 0,

  data: {
    articleId: '',
    state: 'loading',
    stateMessage: '',
    article: null
  },

  onLoad(options = {}) {
    let articleId
    try {
      articleId = normalizeArticleId(options.articleId)
    } catch (error) {
      this.setData({
        articleId: '',
        state: 'not-found',
        stateMessage: '文章地址无效，请返回文章列表重新选择',
        article: null
      })
      return
    }

    this.setData({ articleId })
    this.loadArticle()
  },

  onUnload() {
    this.requestVersion += 1
  },

  async loadArticle() {
    if (!this.data.articleId) return
    const version = ++this.requestVersion
    this.setData({ state: 'loading', stateMessage: '', article: null })

    try {
      const payload = await articleService.getArticle(this.data.articleId)
      if (version !== this.requestVersion) return
      this.setData({
        state: 'success',
        stateMessage: '',
        article: adaptArticleDetail(payload)
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      const notFound = error && error.kind === 'NOT_FOUND'
      this.setData({
        state: notFound ? 'not-found' : 'recoverable-error',
        stateMessage: notFound
          ? '文章已下架或不存在'
          : (error && error.message ? error.message : '文章加载失败，请稍后重试'),
        article: null
      })
    }
  },

  retry() {
    this.loadArticle()
  },

  handleBack() {
    if (typeof getCurrentPages === 'function' && getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 })
      return
    }
    wx.switchTab({ url: '/pages/home/index' })
  }
})

const articleService = require('../../services/article-service')
const { normalizeArticleId, adaptArticleDetail, createArticleShare } = require('../../models/article')

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

  previewArticleImage(event) {
    const current = event && event.currentTarget && event.currentTarget.dataset
      ? event.currentTarget.dataset.src
      : ''
    this.previewImage(current)
  },

  previewContentImage(event) {
    const node = event && event.detail && event.detail.node
    const nodeAttributes = node && node.attrs ? node.attrs : {}
    const nodeSource = node && String(node.name || '').toLowerCase() === 'img'
      ? (nodeAttributes.src || nodeAttributes['data-preview-src'] || nodeAttributes['data-src'])
      : ''
    const dataset = event && event.target && event.target.dataset ? event.target.dataset : {}
    const currentTargetDataset = event && event.currentTarget && event.currentTarget.dataset
      ? event.currentTarget.dataset
      : {}
    this.previewImage(
      nodeSource
      || currentTargetDataset.src
      || currentTargetDataset.previewSrc
      || dataset.previewSrc
      || dataset['preview-src']
      || dataset.src
      || dataset['data-src']
      || ''
    )
  },

  previewImage(current) {
    const article = this.data.article
    const urls = article && Array.isArray(article.imageUrls) ? article.imageUrls : []
    if (!current || !urls.includes(current) || typeof wx.previewImage !== 'function') return
    wx.previewImage({ current, urls })
  },

  onShareAppMessage() {
    return createArticleShare(this.data.state === 'success' ? this.data.article : null)
  },

  onShareTimeline() {
    const share = this.onShareAppMessage()
    return {
      title: share.title,
      query: share.path.split('?')[1] || '',
      imageUrl: share.imageUrl
    }
  },

  handleBack() {
    if (typeof getCurrentPages === 'function' && getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 })
      return
    }
    wx.switchTab({ url: '/pages/home/index' })
  }
})

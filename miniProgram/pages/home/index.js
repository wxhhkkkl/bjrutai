const { getCurrentSession, getEntry } = require('../../services/session-service')
const workbenchService = require('../../services/workbench-service')
const articleService = require('../../services/article-service')
const {
  adaptWorkbench,
  adaptNotices,
  adaptRecentBindings,
  buildHomeViewModel
} = require('../../models/workbench')
const { normalizeArticleId, adaptArticlePage } = require('../../models/article')
const { openAction, updateTabBar } = require('../../services/navigation-service')

function errorState(error) {
  return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error'
}

Page({
  requestVersion: 0,
  articleRequestVersion: 0,

  data: {
    session: {},
    state: 'loading',
    stateMessage: '',
    summary: {},
    notices: [],
    records: [],
    articleState: 'loading',
    articleStateMessage: '',
    articleItems: [],
    openingArticleId: ''
  },

  onShow() {
    const session = getCurrentSession()
    const entry = getEntry(session)

    if (entry.type === 'reLaunch') {
      wx.reLaunch({ url: entry.url })
      return
    }

    updateTabBar(this, 'home')
    if (this.data.openingArticleId) this.setData({ openingArticleId: '' })
    this.loadWorkbench(session)
    this.loadArticles()
  },

  onHide() {
    this.requestVersion += 1
    this.articleRequestVersion += 1
  },

  onUnload() {
    this.requestVersion += 1
    this.articleRequestVersion += 1
  },

  async loadWorkbench(session) {
    const version = ++this.requestVersion
    this.setData({ session, state: 'loading', stateMessage: '' })

    try {
      const [workbenchPayload, noticesPayload, bindingsPayload] = await Promise.all([
        workbenchService.getWorkbench(session.userId),
        workbenchService.getNotices(session.userId),
        workbenchService.getRecentBindings(session.userId)
      ])
      if (version !== this.requestVersion) return

      const workbench = adaptWorkbench(workbenchPayload)
      const notices = adaptNotices(noticesPayload)
      const records = adaptRecentBindings(bindingsPayload)
      this.setData({
        state: workbench.role === 'unknown' ? 'empty' : 'success',
        stateMessage: workbench.role === 'unknown' ? '暂无可展示的工作台数据' : '',
        summary: buildHomeViewModel(workbench),
        notices,
        records
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({
        state: errorState(error),
        stateMessage: error && error.message ? error.message : '请稍后再试'
      })
    }
  },

  retry() {
    this.loadWorkbench(getCurrentSession())
  },

  async loadArticles() {
    const version = ++this.articleRequestVersion
    this.setData({
      articleState: 'loading',
      articleStateMessage: '',
      articleItems: []
    })

    try {
      const payload = await articleService.listArticles({ limit: 3 })
      if (version !== this.articleRequestVersion) return
      const page = adaptArticlePage(payload)
      this.setData({
        articleState: page.items.length ? 'success' : 'empty',
        articleStateMessage: page.items.length ? '' : '暂无已发布文章',
        articleItems: page.items.slice(0, 3)
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

  handleScan(e) {
    wx.showModal({
      title: '扫码结果',
      content: e.detail.result || '识别成功',
      showCancel: false
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

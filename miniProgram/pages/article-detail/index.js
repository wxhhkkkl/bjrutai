const articleService = require('../../services/article-service')
const commentService = require('../../services/comment-service')
const sessionService = require('../../services/session-service')
const { adaptCommentPage, adaptLikeResult } = require('../../models/comment')
const { normalizeArticleId, adaptArticleDetail, createArticleShare } = require('../../models/article')

Page({
  requestVersion: 0,

  data: {
    articleId: '',
    state: 'loading',
    stateMessage: '',
    article: null,
    commentsVisible: false,
    commentsState: 'hidden',
    comments: [],
    commentsTotal: 0,
    commentsNextCursor: '',
    commentsHasMore: false,
    commentsLoadingMore: false,
    commentsError: '',
    commentDraft: '',
    commentSubmitting: false,
    commentSubmitMessage: '',
    commentBusyId: ''
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
    this.syncCommentVisibility()
  },

  onUnload() {
    this.requestVersion += 1
  },

  syncCommentVisibility() {
    const loggedIn = Boolean(sessionService.getAccessToken())
    this.setData({
      commentsVisible: loggedIn,
      commentsState: loggedIn ? 'loading' : 'hidden',
      commentsError: loggedIn ? this.data.commentsError : '',
      commentSubmitMessage: loggedIn ? this.data.commentSubmitMessage : ''
    })
    if (loggedIn && this.data.articleId && this.data.state === 'success' && !this.data.comments.length) {
      this.loadComments(false)
    }
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
      this.syncCommentVisibility()
      if (sessionService.getAccessToken()) this.loadComments(false)
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

  async loadComments(loadMore) {
    if (!this.data.articleId || !sessionService.getAccessToken()) return
    if (loadMore && (!this.data.commentsHasMore || this.data.commentsLoadingMore)) return
    const version = this.requestVersion
    const cursor = loadMore ? this.data.commentsNextCursor : ''
    this.setData(loadMore
      ? { commentsLoadingMore: true, commentsError: '' }
      : { commentsState: 'loading', commentsError: '', comments: [], commentsNextCursor: '', commentsHasMore: false })
    try {
      const payload = await commentService.listComments(this.data.articleId, { cursor, limit: 20 })
      if (version !== this.requestVersion) return
      const page = adaptCommentPage(payload)
      const comments = loadMore ? this.data.comments.concat(page.items) : page.items
      this.setData({
        commentsVisible: true,
        commentsState: comments.length ? 'success' : 'empty',
        comments,
        commentsTotal: page.total,
        commentsNextCursor: page.nextCursor,
        commentsHasMore: page.hasMore,
        commentsLoadingMore: false,
        commentsError: ''
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      const authExpired = error && error.kind === 'AUTH'
      this.setData({
        commentsVisible: !authExpired,
        commentsState: authExpired ? 'hidden' : 'error',
        commentsError: authExpired ? '' : (error && error.message ? error.message : '评论加载失败，请重试'),
        commentsLoadingMore: false
      })
    }
  },

  retryComments() {
    this.loadComments(false)
  },

  loadMoreComments() {
    this.loadComments(true)
  },

  handleCommentInput(event) {
    this.setData({ commentDraft: event.detail && event.detail.value ? event.detail.value : '' })
  },

  async submitComment() {
    if (!sessionService.getAccessToken()) {
      this.promptCommentLogin()
      return
    }
    const content = String(this.data.commentDraft || '').trim()
    if (!content || content.length > 500) {
      this.setData({ commentSubmitMessage: '评论内容需为 1–500 个字符' })
      return
    }
    if (this.data.commentSubmitting) return
    this.setData({ commentSubmitting: true, commentSubmitMessage: '' })
    try {
      const result = await commentService.createComment(this.data.articleId, content)
      const pending = result && result.status === 'pending'
      this.setData({
        commentDraft: '',
        commentSubmitMessage: pending ? '评论已提交，审核通过后展示' : '评论已发布',
        commentSubmitting: false
      })
      if (!pending) this.loadComments(false)
    } catch (error) {
      this.setData({
        commentSubmitting: false,
        commentSubmitMessage: error && error.message ? error.message : '评论提交失败，请重试'
      })
    }
  },

  promptCommentLogin() {
    wx.navigateTo({ url: '/pages/auth/login/index' })
  },

  async toggleCommentLike(event) {
    const commentId = event.currentTarget.dataset.commentId
    const item = this.data.comments.find((comment) => comment.commentId === String(commentId))
    if (!item || this.data.commentBusyId) return
    this.setData({ commentBusyId: item.commentId })
    try {
      const result = item.liked
        ? await commentService.unlikeComment(this.data.articleId, item.commentId)
        : await commentService.likeComment(this.data.articleId, item.commentId)
      const adapted = adaptLikeResult(result)
      this.setData({
        comments: this.data.comments.map((comment) => (
          comment.commentId === adapted.commentId
            ? Object.assign({}, comment, { liked: adapted.liked, likeCount: adapted.likeCount })
            : comment
        )),
        commentBusyId: ''
      })
    } catch (error) {
      this.setData({
        commentBusyId: '',
        commentsError: error && error.message ? error.message : '点赞操作失败，请重试'
      })
    }
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

  onShow() {
    this.syncCommentVisibility()
  },

  handleBack() {
    if (typeof getCurrentPages === 'function' && getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 })
      return
    }
    wx.switchTab({ url: '/pages/home/index' })
  }
})

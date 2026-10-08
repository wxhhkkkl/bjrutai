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
    videoError: false,
    videoLoading: false,
    videoMounted: true,
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
    this.pauseVideo()
    this.requestVersion += 1
  },

  onHide() {
    this.pauseVideo()
  },

  pauseVideo() {
    if (this.data.article && this.data.article.video && typeof wx.createVideoContext === 'function') {
      wx.createVideoContext('articleVideo', this).pause()
    }
  },

  onVideoError() {
    this.setData({ videoError: true, videoLoading: false })
  },

  onVideoWaiting() {
    if (!this.data.videoLoading) this.setData({ videoLoading: true })
  },

  onVideoReady() {
    if (this.data.videoLoading) this.setData({ videoLoading: false })
  },

  retryVideo() {
    if (!this.data.article || !this.data.article.video) return
    this.setData({ videoMounted: false, videoError: false, videoLoading: false }, () => {
      this.setData({ videoMounted: true })
    })
  },

  syncCommentVisibility() {
    const loggedIn = Boolean(sessionService.getAccessToken())
    if (!loggedIn) {
      this.setData({
        commentsVisible: false,
        commentsState: 'hidden',
        comments: [],
        commentsTotal: 0,
        commentsNextCursor: '',
        commentsHasMore: false,
        commentsLoadingMore: false,
        commentsError: '',
        commentDraft: '',
        commentSubmitMessage: ''
      })
      return
    }
    const shouldLoad = this.data.articleId && this.data.state === 'success'
      && (!this.data.commentsVisible || this.data.commentsState === 'hidden')
    this.setData({
      commentsVisible: true,
      commentsState: shouldLoad ? 'loading' : this.data.commentsState
    })
    if (shouldLoad) this.loadComments(false)
  },

  async loadArticle() {
    if (!this.data.articleId) return
    this.pauseVideo()
    const version = ++this.requestVersion
    this.setData({ state: 'loading', stateMessage: '', article: null, videoError: false, videoLoading: false, videoMounted: true })

    try {
      const payload = await articleService.getArticle(this.data.articleId)
      if (version !== this.requestVersion) return
      this.setData({
        state: 'success',
        stateMessage: '',
        article: adaptArticleDetail(payload)
      })
      this.syncCommentVisibility()
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

  async loadComments(loadMore) {
    const accessToken = sessionService.getAccessToken()
    if (!this.data.articleId || !accessToken) return
    if (loadMore && (!this.data.commentsHasMore || this.data.commentsLoadingMore)) return
    const version = this.requestVersion
    const cursor = loadMore ? this.data.commentsNextCursor : ''
    this.setData(loadMore
      ? { commentsLoadingMore: true, commentsError: '' }
      : { commentsState: 'loading', commentsError: '', comments: [], commentsNextCursor: '', commentsHasMore: false })
    try {
      const payload = await commentService.listComments(this.data.articleId, { cursor, limit: 20 })
      if (version !== this.requestVersion || sessionService.getAccessToken() !== accessToken) return
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
      if (version !== this.requestVersion || sessionService.getAccessToken() !== accessToken) return
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
    wx.navigateTo({ url: `/pages/auth/login/index?from=comment&articleId=${this.data.articleId}` })
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

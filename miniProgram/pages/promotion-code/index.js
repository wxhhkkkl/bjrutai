const promotionService = require('../../services/promotion-service')
const { PROMOTION_STEPS, createPromotionShare } = require('../../models/promotion-code')
const { getCurrentSession } = require('../../services/session-service')

Page({
  data: { state: 'loading', stateMessage: '', profile: {}, statistics: {}, steps: PROMOTION_STEPS, saving: false },
  onLoad() { this.loadPromotion() },
  async loadPromotion() { try { const [code, statistics, poster] = await Promise.all([promotionService.getPromotionCode(), promotionService.getStatistics('30d'), promotionService.getPoster()]); const value = { ...code, ...(poster || {}), name: code.name || getCurrentSession().name || '', roleLabel: '市场拓展人', qrImage: code.qrUrl || code.qrImage || (poster && poster.imageUrl) || '' }; this.setData({ state: 'success', profile: value, statistics: statistics || {} }) } catch (error) { this.setData({ state: error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error', stateMessage: error.message || '推广码暂不可用' }) } },
  retry() { this.loadPromotion() },
  handleBack() { if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 }); else wx.switchTab({ url: '/pages/profile/index' }) },
  savePromotionCode() { if (!this.data.profile.qrImage) { wx.showToast({ title: '后端未返回推广码图片', icon: 'none' }); return } wx.showToast({ title: '请使用微信保存图片功能', icon: 'none' }) },
  onShareAppMessage() { return createPromotionShare(this.data.profile) },
  onShareTimeline() { const share = createPromotionShare(this.data.profile); return { title: share.title, query: `sourceId=${this.data.profile.id}`, imageUrl: share.imageUrl } }
})

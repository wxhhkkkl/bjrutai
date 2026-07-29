const {
  getCurrentSession
} = require('../../services/session-service');
const {
  PROMOTION_STEPS,
  getPromotionProfile,
  createPromotionShare
} = require('../../models/promotion-code');

Page({
  data: {
    profile: getPromotionProfile(),
    steps: PROMOTION_STEPS,
    saving: false
  },

  onLoad() {
    this.setData({
      profile: getPromotionProfile(getCurrentSession())
    });
  },

  handleBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.switchTab({ url: '/pages/profile/index' });
  },

  savePromotionCode() {
    if (this.data.saving) return;

    this.setData({ saving: true });
    wx.showLoading({ title: '正在保存', mask: true });

    wx.getImageInfo({
      src: this.data.profile.qrImage,
      success: ({ path }) => {
        wx.saveImageToPhotosAlbum({
          filePath: path,
          success: () => {
            wx.showToast({
              title: '已保存到相册',
              icon: 'success'
            });
          },
          fail: (error) => {
            this.handleSaveFailure(error);
          },
          complete: () => {
            wx.hideLoading();
            this.setData({ saving: false });
          }
        });
      },
      fail: () => {
        wx.hideLoading();
        this.setData({ saving: false });
        wx.showToast({
          title: '图片读取失败，请重试',
          icon: 'none'
        });
      }
    });
  },

  handleSaveFailure(error = {}) {
    const denied = /auth deny|authorize:fail/i.test(error.errMsg || '');

    if (!denied) {
      wx.showToast({
        title: '保存失败，请重试',
        icon: 'none'
      });
      return;
    }

    wx.showModal({
      title: '需要相册权限',
      content: '请允许访问相册，以保存专属推广二维码。',
      confirmText: '去设置',
      success: ({ confirm }) => {
        if (confirm) wx.openSetting();
      }
    });
  },

  onShareAppMessage() {
    return createPromotionShare(this.data.profile);
  },

  onShareTimeline() {
    const share = createPromotionShare(this.data.profile);

    return {
      title: share.title,
      query: `sourceId=${this.data.profile.id}`,
      imageUrl: share.imageUrl
    };
  }
});

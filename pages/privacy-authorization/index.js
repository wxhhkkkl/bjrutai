const {
  getCurrentSession
} = require('../../services/session-service');
const {
  PRIVACY_DOCUMENTS,
  createPrivacySettings,
  getAuthorizationView,
  getPrivacyDocument
} = require('../../models/privacy-authorization');

const PRIVACY_SETTINGS_KEY = 'lutai_privacy_settings';

Page({
  data: {
    documents: PRIVACY_DOCUMENTS,
    authorization: getAuthorizationView(),
    settings: createPrivacySettings(),
    saving: false
  },

  onLoad() {
    this.setData({
      settings: createPrivacySettings(
        wx.getStorageSync(PRIVACY_SETTINGS_KEY)
      )
    });
    this.refreshAuthorization();
  },

  onShow() {
    this.refreshAuthorization();
  },

  handleBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.switchTab({
      url: '/pages/profile/index'
    });
  },

  refreshAuthorization() {
    const session = getCurrentSession();

    if (!wx.getSetting) {
      this.setData({
        authorization: getAuthorizationView(session)
      });
      return;
    }

    wx.getSetting({
      withSubscriptions: true,
      success: (result) => {
        const authSetting = result.authSetting || {};
        const subscription = result.subscriptionsSetting || {};

        this.setData({
          authorization: getAuthorizationView(session, {
            camera: authSetting['scope.camera'],
            album: authSetting['scope.writePhotosAlbum'],
            customerMessage: subscription.mainSwitch === true
          })
        });
      },
      fail: () => {
        this.setData({
          authorization: getAuthorizationView(session)
        });
      }
    });
  },

  openPhoneAuthorization() {
    wx.navigateTo({
      url: '/pages/account-profile/index'
    });
  },

  openSystemAuthorization() {
    if (!wx.openSetting) {
      wx.showToast({
        title: '当前微信版本暂不支持授权设置',
        icon: 'none'
      });
      return;
    }

    wx.openSetting({
      success: () => {
        this.refreshAuthorization();
      },
      fail: () => {
        wx.showToast({
          title: '未能打开微信授权设置',
          icon: 'none'
        });
      }
    });
  },

  togglePrivacySetting(event) {
    const field = event.currentTarget.dataset.field;
    const patch = {};

    patch[`settings.${field}`] = event.detail.value;
    this.setData(patch);
  },

  openDocument(event) {
    const document = getPrivacyDocument(event.currentTarget.dataset.id);

    if (!document) return;
    wx.showModal({
      title: document.title,
      content: document.content,
      showCancel: false,
      confirmText: '知道了'
    });
  },

  revokeNonEssentialAuthorization() {
    wx.showModal({
      title: '撤回非必要授权',
      content: '您可以关闭个性化服务，并在微信授权设置中管理相机、相册及消息授权。',
      confirmText: '管理授权',
      success: ({ confirm }) => {
        if (!confirm) return;

        this.setData({
          'settings.personalized': false
        });
        this.openSystemAuthorization();
      }
    });
  },

  saveSettings() {
    if (this.data.saving) return;
    this.setData({ saving: true });
    wx.setStorageSync(PRIVACY_SETTINGS_KEY, this.data.settings);
    wx.showToast({
      title: '设置已保存',
      icon: 'success',
      duration: 900
    });

    setTimeout(() => {
      this.setData({ saving: false });
      this.handleBack();
    }, 500);
  }
});

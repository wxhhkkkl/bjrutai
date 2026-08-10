const {
  getCurrentSession
} = require('../../services/session-service');
const {
  PRIVACY_DOCUMENTS,
  createPrivacySettings,
  getAuthorizationView,
  getPrivacyDocument
} = require('../../models/privacy-authorization');
const complianceService = require('../../services/compliance-service');

const PRIVACY_SETTINGS_KEY = 'lutai_privacy_settings';

function isLegacyVersionValidation(error) {
  return Boolean(error && (
    error.httpStatus === 422 ||
    error.code === 422 ||
    error.code === 42200
  ));
}

async function savePrivacySettingsCompat(settings) {
  try {
    return await complianceService.updatePrivacySettings(settings);
  } catch (error) {
    if (!isLegacyVersionValidation(error)) throw error;

    const latest = await complianceService.getLatestAgreements();
    const items = Array.isArray(latest && latest.items) ? latest.items : [];
    const privacy = items.find((item) => {
      const type = String(item.type || '').toLowerCase();
      const title = String(item.title || '');
      return type === 'privacy' ||
        type === 'privacy_policy' ||
        type.includes('privacy') ||
        /隐私|privacy/i.test(title);
    });
    const versions = items
      .map((item) => Number(item.version))
      .filter((value) => Number.isInteger(value) && value >= 1);
    const version = Number(privacy && privacy.version) || Math.max(...versions, 1);

    return complianceService.updatePrivacySettings(Object.assign({}, settings, { version }));
  }
}

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
    this.loadConsents();
  },

  onShow() {
    this.refreshAuthorization();
  },

  async loadConsents() {
    try {
      const result = await complianceService.getConsents();
      this.setData({ consents: result.items || [] });
    } catch (error) {
      this.setData({ consents: [] });
    }
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
    const type = event.currentTarget.dataset.id;
    if (type === 'agreement' || type === 'privacy') {
      wx.navigateTo({ url: `/pages/legal-document/index?type=${type}` });
      return;
    }
    const document = getPrivacyDocument(type);
    if (document) {
      wx.showModal({
        title: document.title,
        content: document.content,
        showCancel: false,
        confirmText: '知道了'
      });
    }
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

  async saveSettings() {
    if (this.data.saving) return;
    this.setData({ saving: true });
    const settings = createPrivacySettings(this.data.settings);

    try {
      await savePrivacySettingsCompat({
        maskSensitive: settings.maskSensitive,
        personalized: settings.personalized
      });
      wx.setStorageSync(PRIVACY_SETTINGS_KEY, settings);
      wx.showToast({ title: '设置已保存', icon: 'success' });
      setTimeout(() => this.handleBack(), 700);
    } catch (error) {
      wx.showToast({ title: error.message || '保存失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  }
});

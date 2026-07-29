const {
  DEFAULT_NAVIGATION,
  getNavigationLayout
} = require('../../utils/navigation-layout');

Component({
  properties: {
    title: {
      type: String,
      value: ''
    },
    showLogo: {
      type: Boolean,
      value: false
    },
    showScan: {
      type: Boolean,
      value: false
    },
    spacerOnly: {
      type: Boolean,
      value: false
    }
  },

  data: {
    navigation: { ...DEFAULT_NAVIGATION }
  },

  lifetimes: {
    attached() {
      this.updateNavigationLayout();
    }
  },

  pageLifetimes: {
    resize() {
      this.updateNavigationLayout();
    }
  },

  methods: {
    updateNavigationLayout() {
      this.setData({ navigation: getNavigationLayout() });
    },

    scanCode() {
      wx.scanCode({
        success: (result) => {
          this.triggerEvent('scan', result);
        },
        fail: (error) => {
          const errMsg = error.errMsg || '';

          if (errMsg.includes('cancel')) {
            return;
          }

          wx.showToast({
            title: '扫码失败，请重试',
            icon: 'none'
          });
          this.triggerEvent('scanerror', error);
        }
      });
    }
  }
});

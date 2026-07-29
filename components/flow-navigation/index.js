const {
  DEFAULT_NAVIGATION,
  getNavigationLayout
} = require('../../utils/navigation-layout');

Component({
  properties: {
    title: {
      type: String,
      value: ''
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

    goBack() {
      this.triggerEvent('back');
    }
  }
});

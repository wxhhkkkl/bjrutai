const {
    getVisibleTabs
} = require('../models/navigation')
const { getCurrentSession, getAccessToken } = require('../services/session-service')
Component({
    data: {
        selected: 'home',
        tabs: []
    },
    lifetimes: {
        attached() {
            this.setData({ tabs: getVisibleTabs(getCurrentSession()) })
        }
    },
    methods: {
        switchTab(e) {
            const item = e.currentTarget.dataset.item;
            if (!item) return;
            if (item.id === this.data.selected) return;
            if (item.id === 'profile' && (!getAccessToken() || !getCurrentSession().userId)) {
                wx.navigateTo({ url: '/pages/auth/login/index?from=profile' });
                return;
            }
            wx.switchTab({
                url: item.pagePath
            })
        }
    }
})

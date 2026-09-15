const {
    getVisibleTabs
} = require('../models/navigation')
const { getCurrentSession } = require('../services/session-service')
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
            if (item.id === this.data.selected) return;
            wx.switchTab({
                url: item.pagePath
            })
        }
    }
})

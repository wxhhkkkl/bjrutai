const {
    TAB_ITEMS
} = require('../models/navigation')
Component({
    data: {
        selected: 'home',
        tabs: TAB_ITEMS
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
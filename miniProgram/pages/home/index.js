const { getCurrentSession, getEntry } = require('../../services/session-service');
const { summaries } = require('../../mock/foundation-fixtures');
const demo = require('../../mock/demo-control');
const { openAction, updateTabBar } = require('../../services/navigation-service');

Page({
    data: {
        session: {},
        state: 'success',
        summary: {},
        records: []
    },

    onShow() {
        const session = getCurrentSession();
        const entry = getEntry(session);

        if (entry.type === 'reLaunch') {
            wx.reLaunch({ url: entry.url });
            return;
        }

        this.setData({
            session,
            state: demo.getPageViewState('home'),
            summary: summaries.promoter,
            records: summaries.customers
        });
        updateTabBar(this, 'home');
    },

    retry() {
        demo.setPageViewState('home', 'success');
        this.onShow();
    },

    handleScan(e) {
        wx.showModal({
            title: '扫码结果',
            content: e.detail.result || '识别成功',
            showCancel: false
        });
    },

    action(e) {
        const result = openAction(
            e.currentTarget.dataset.id,
            this.data.session
        );

        if (result.ok) {
            wx.navigateTo({ url: result.url });
        } else {
            wx.showToast({ title: result.message, icon: 'none' });
        }
    }
});

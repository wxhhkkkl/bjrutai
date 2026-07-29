// pages/index/index.js
const {
    getCurrentSession,
    getEntry
} = require('../../services/session-service')
Page({
    onShow() {
        const entry = getEntry(getCurrentSession());
        if (entry.type === 'switchTab') wx.switchTab({
            url: entry.url
        });
        else wx.reLaunch({
            url: entry.url
        })
    }
})
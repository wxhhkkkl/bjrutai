const {
    getCurrentSession
} = require('../../services/session-service');
const {
    summaries
} = require('../../mock/foundation-fixtures');
const demo = require('../../mock/demo-control');
const {
    updateTabBar,
    openAction
} = require('../../services/navigation-service');
const {
    getIdentityLabel
} = require('../../models/collaborator');

const SERVICE_ITEMS = [{
        id: 'promote-code',
        title: '我的推广码',
        description: '邀请客户进入儒泰',
        icon: '/assets/images/profile-promo-icon.png'
    },
    {
        id: 'qualification',
        title: '资质状态',
        description: '审核通过',
        icon: '/assets/images/profile-qualification-icon.png'
    },
    {
        id: 'binding-records',
        title: '绑定记录',
        description: '查看客户绑定状态',
        icon: '/assets/images/profile-records-icon.png'
    },
    {
        id: 'contribution-detail',
        title: '贡献明细',
        description: '查看每笔贡献来源',
        icon: '/assets/images/profile-contribution-icon.png'
    }
];

const ACCOUNT_ITEMS = [{
        id: 'profile',
        title: '账号信息',
        icon: '/assets/images/profile-account-icon.png'
    },
    {
        id: 'help-feedback',
        title: '帮助与反馈',
        icon: '/assets/images/profile-help-icon.png'
    },
    {
        id: 'privacy',
        title: '隐私与授权',
        icon: '/assets/images/profile-privacy-icon.png'
    }
];

Page({
    data: {
        state: 'success',
        session: {},
        identityLabel: '鲁泰协作人员',
        metrics: [],
        serviceItems: SERVICE_ITEMS,
        accountItems: ACCOUNT_ITEMS
    },

    onShow() {
        const session = getCurrentSession();
        const summary = summaries.promoter;

        this.setData({
            state: demo.getPageViewState('profile'),
            session,
            identityLabel: getIdentityLabel(session),
            metrics: [{
                    label: '客户',
                    value: '36'
                },
                {
                    label: '本月贡献',
                    value: summary.monthlyContribution
                },
                {
                    label: '累计服务',
                    value: '28'
                }
            ]
        });
        updateTabBar(this, 'profile');
    },

    retry() {
        demo.setPageViewState('profile', 'success');
        this.onShow();
    },

    action(e) {
        const result = openAction(
            e.currentTarget.dataset.id,
            this.data.session
        );

        if (result.ok) {
            wx.navigateTo({
                url: result.url
            });
        } else {
            wx.showToast({
                title: result.message,
                icon: 'none'
            });
        }
    },

    logout() {
        wx.showModal({
            title: '退出登录',
            content: '确认退出当前账号吗？',
            confirmText: '退出',
            confirmColor: '#ef2929',
            success: ({
                confirm
            }) => {
                if (!confirm) {
                    return;
                }

                demo.resetDemoControl();
                wx.reLaunch({
                    url: '/pages/auth/login/index'
                });
            }
        });
    }
});

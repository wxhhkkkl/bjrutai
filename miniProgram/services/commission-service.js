/**
 * Commission/performance service (008, US3).
 *
 * Promoter: GET /my/performance/commission — own estimate + confirmed months.
 * Org admin: GET /org/performance/commission — managed org subtree view.
 * Only commission amounts (base/ratio/amount) are returned (FR-009).
 */
const USE_MOCK = false;

const MOCK_MY_COMMISSION = {
  currentMonth: {
    month: '2026-08',
    status: 'estimate',
    intraOrg: { baseCent: 800000, ratio: 0.05, commissionCent: 40000 },
    orgManagement: null,
  },
  confirmed: [
    { month: '2026-07', status: 'confirmed', intraOrg: { baseCent: 750000, ratio: 0.05, commissionCent: 37500 }, orgManagement: null },
  ],
};

const { getAccessToken } = require('./auth-service');

function _request(url, data) {
  if (USE_MOCK) {
    return Promise.resolve(url.includes('/my/') ? MOCK_MY_COMMISSION : {});
  }
  const apiBase = getApp().globalData.apiBase || 'http://127.0.0.1:8000';
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase}${url}`,
      method: 'GET',
      data,
      header: { Authorization: `Bearer ${getAccessToken()}` },
      success: (res) => {
        const body = res.data || {};
        if (body.code === 0) resolve(body.data);
        else reject(new Error(body.message || '获取绩效失败'));
      },
      fail: () => reject(new Error('网络异常，请稍后重试')),
    });
  });
}

function requestMyCommission({ month } = {}) {
  return _request('/api/v1/my/performance/commission', { month });
}

function requestOrgCommission({ month } = {}) {
  return _request('/api/v1/org/performance/commission', { month });
}

module.exports = { requestMyCommission, requestOrgCommission };

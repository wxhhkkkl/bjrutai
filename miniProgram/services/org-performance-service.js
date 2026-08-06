/**
 * Org performance API service (US5).
 *
 * Fetches the org-admin's authorized org subtree 消费金额 summary from
 * the backend (amounts in cents). Set USE_MOCK = true to run the demo.
 */
const USE_MOCK = false;

const MOCK_PERFORMANCE = {
  orgId: 'org_1001',
  orgName: '北京儒泰总部',
  period: '2026-08',
  summary: { thisMonth: 12500000, cumulative: 86000000 },
  subOrgs: [
    { orgId: 'org_1002', orgName: '华北区', thisMonth: 5200000, cumulative: 31000000 },
    { orgId: 'org_1003', orgName: '华东区', thisMonth: 4800000, cumulative: 29000000 },
  ],
  members: [
    { distributorId: 'd_1001', orgId: 'org_1002', name: '张三', thisMonth: 2300000, cumulative: 15000000 },
    { distributorId: 'd_1002', orgId: 'org_1002', name: '李四', thisMonth: 1800000, cumulative: 9600000 },
    { distributorId: 'd_1003', orgId: 'org_1003', name: '王五', thisMonth: 2100000, cumulative: 11200000 },
  ],
};

const { getAccessToken } = require('./auth-service');

function requestOrgPerformance({ month } = {}) {
  if (USE_MOCK) {
    return Promise.resolve({
      ...MOCK_PERFORMANCE,
      period: month || MOCK_PERFORMANCE.period,
    });
  }

  const apiBase = getApp().globalData.apiBase || 'http://127.0.0.1:8000';
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase}/api/v1/org/performance`,
      method: 'GET',
      data: { month },
      header: { Authorization: `Bearer ${getAccessToken()}` },
      success: (res) => {
        const body = res.data || {};
        if (body.code === 0) resolve(body.data);
        else reject(new Error(body.message || '获取组织业绩失败'));
      },
      fail: () => reject(new Error('网络异常，请稍后重试')),
    });
  });
}

module.exports = { requestOrgPerformance };

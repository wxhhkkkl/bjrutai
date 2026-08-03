/**
 * Org performance API service (US5).
 *
 * Fetches the org-admin's authorized org subtree contribution summary from
 * the backend. The mini-program demo uses mock data by default; set
 * USE_MOCK = false to call the real endpoint.
 */
const USE_MOCK = true;

const MOCK_PERFORMANCE = {
  orgId: 'org_1001',
  orgName: '北京儒泰总部',
  period: '2026-08',
  summary: { thisMonth: 125000, cumulative: 860000 },
  subOrgs: [
    { orgId: 'org_1002', orgName: '华北区', thisMonth: 52000, cumulative: 310000 },
    { orgId: 'org_1003', orgName: '华东区', thisMonth: 48000, cumulative: 290000 },
  ],
  members: [
    { distributorId: 'd_1001', orgId: 'org_1002', name: '张三', thisMonth: 23000, cumulative: 150000 },
    { distributorId: 'd_1002', orgId: 'org_1002', name: '李四', thisMonth: 18000, cumulative: 96000 },
    { distributorId: 'd_1003', orgId: 'org_1003', name: '王五', thisMonth: 21000, cumulative: 112000 },
  ],
};

function requestOrgPerformance({ month } = {}) {
  if (USE_MOCK) {
    return Promise.resolve({
      ...MOCK_PERFORMANCE,
      period: month || MOCK_PERFORMANCE.period,
    });
  }

  const token = wx.getStorageSync('token');
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApp().globalData.apiBase || 'https://api.example.com'}/api/v1/org/performance`,
      method: 'GET',
      data: { month },
      header: { Authorization: `Bearer ${token}` },
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

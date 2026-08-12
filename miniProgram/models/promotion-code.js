const PROMOTION_CODE = Object.freeze({
  sourceCity: '北京',
  available: true,
  qrImage: '/assets/images/promotion-qr.jpg'
});
const {
  getIdentityLabel
} = require('./collaborator');

const PROMOTION_STEPS = Object.freeze([
  {
    id: 'scan',
    icon: 'scan',
    label: '客户扫描二维码'
  },
  {
    id: 'open',
    icon: 'miniprogram-o',
    label: '进入儒泰小程序'
  },
  {
    id: 'confirm',
    icon: 'friends-o',
    label: '医生完成客户归属确认'
  }
]);

function getPromotionProfile(session = {}) {
  return {
    ...PROMOTION_CODE,
    id: session.userId || 'demo-collaborator-001',
    name: session.name || '张小明',
    roleLabel: getIdentityLabel(session),
    statusLabel: PROMOTION_CODE.available ? '推广码可用' : '推广码已停用'
  };
}

function createPromotionShare(profile) {
  const value = profile || getPromotionProfile();
  const fallbackPath = `/pages/home/index?sourceId=${encodeURIComponent(value.id || '')}`;

  return {
    title: value.shareTitle || `${value.name}邀请你进入儒泰小程序`,
    path: value.sharePath || fallbackPath,
    imageUrl: value.qrImage
  };
}

module.exports = {
  PROMOTION_CODE,
  PROMOTION_STEPS,
  getPromotionProfile,
  createPromotionShare
};

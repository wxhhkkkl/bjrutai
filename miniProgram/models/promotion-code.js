const PROMOTION_CODE = Object.freeze({
  sourceCity: '北京',
  available: true,
  qrImage: ''
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
    label: '授权手机号并完成归属'
  }
]);

function getPromotionProfile(session = {}) {
  return {
    ...PROMOTION_CODE,
    id: session.userId || '',
    name: session.name || '',
    roleLabel: getIdentityLabel(session),
    statusLabel: PROMOTION_CODE.available ? '客户绑定码可用' : '客户绑定码已停用'
  };
}

function createPromotionShare(profile) {
  const value = profile || getPromotionProfile();
  const fallbackPath = `/pages/patient-binding/index?refToken=${encodeURIComponent(value.refToken || '')}`;

  return {
    title: value.shareTitle || `${value.name || '儒泰医联业务员'}邀请您完成客户绑定`,
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

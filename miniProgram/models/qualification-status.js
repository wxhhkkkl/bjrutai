const COMMON_INFORMATION = Object.freeze([
  {
    label: '法人主体',
    value: '北京鲁泰服务有限公司'
  },
  {
    label: '资质类型',
    value: '营业执照'
  },
  {
    label: '统一社会信用代码',
    value: '91110108**********'
  }
]);

const QUALIFICATION_STATES = Object.freeze({
  approved: {
    id: 'approved',
    tone: 'green',
    title: '资质审核已通过',
    description: '当前资质有效，可正常开展推广业务',
    badge: '审核通过',
    icon: 'shield-o',
    markIcon: 'passed',
    banner: '/assets/images/qualification-approved-banner.png',
    dateLabel: '有效期至',
    dateValue: '2028年12月31日',
    recordDate: '2025年4月20日',
    recordTitle: '资质审核通过',
    recordDescription: '资料审核已完成',
    noticePrefix: '将在资质到期前',
    noticeHighlight: '30',
    noticeSuffix: '天提醒您续期',
    noticeIcon: 'bell',
    actionIcon: 'edit',
    actionLabel: '更新资质信息',
    actionType: 'update'
  },
  reviewing: {
    id: 'reviewing',
    tone: 'blue',
    title: '资质审核中',
    description: '资料已提交，请耐心等待审核结果',
    badge: '待审核',
    icon: 'description-o',
    markIcon: 'clock-o',
    banner: '/assets/images/qualification-reviewing-banner.png',
    dateLabel: '提交时间',
    dateValue: '2026年7月20日 10:30',
    recordDate: '2026年7月20日',
    recordTitle: '资质已提交',
    recordDescription: '资料正在审核中',
    noticePrefix: '审核期间暂不可使用推广码及贡献相关功能',
    noticeHighlight: '',
    noticeSuffix: '',
    noticeIcon: 'info',
    actionIcon: 'eye-o',
    actionLabel: '查看提交资料',
    actionType: 'view'
  },
  rejected: {
    id: 'rejected',
    tone: 'red',
    title: '资质审核未通过',
    description: '请根据驳回原因修改后重新提交',
    badge: '审核驳回',
    icon: 'description-o',
    markIcon: 'warning-o',
    banner: '/assets/images/qualification-rejected-banner.png',
    dateLabel: '提交时间',
    dateValue: '2026年7月20日 10:30',
    reason: '营业执照有效期信息不清晰，请上传完整、清晰且在有效期内的资质文件。',
    recordDate: '2026年7月21日',
    recordTitle: '资质审核驳回',
    recordDescription: '请修改资料后重新提交',
    noticePrefix: '审核通过前暂不可使用推广码及贡献相关功能',
    noticeHighlight: '',
    noticeSuffix: '',
    noticeIcon: 'bell',
    actionIcon: 'upgrade',
    actionLabel: '重新提交资质',
    actionType: 'update'
  },
  expiring: {
    id: 'expiring',
    tone: 'orange',
    title: '资质即将到期',
    description: '当前资质仍有效，请及时更新续期',
    badge: '剩余 28 天',
    icon: 'shield-o',
    markIcon: 'clock-o',
    banner: '/assets/images/qualification-expiring-banner.png',
    dateLabel: '有效期至',
    dateValue: '2026年8月19日',
    dateWarning: true,
    recordDate: '2025年4月20日',
    recordTitle: '资质审核通过',
    recordDescription: '当前资质仍在有效期内',
    noticePrefix: '资质将在',
    noticeHighlight: '28',
    noticeSuffix: '天后到期，请尽快完成续期',
    noticeIcon: 'bell',
    actionIcon: 'edit',
    actionLabel: '立即更新资质',
    actionType: 'update'
  }
});

const QUALIFICATION_FILE = Object.freeze({
  name: '营业执照.pdf',
  meta: '已上传 · 2.4 MB'
});

function normalizeQualificationState(state) {
  if (QUALIFICATION_STATES[state]) return state;
  return 'reviewing';
}

function getQualificationView(state) {
  const key = normalizeQualificationState(state);

  return {
    ...QUALIFICATION_STATES[key],
    information: [
      ...COMMON_INFORMATION,
      {
        label: QUALIFICATION_STATES[key].dateLabel,
        value: QUALIFICATION_STATES[key].dateValue,
        warning: QUALIFICATION_STATES[key].dateWarning === true
      }
    ],
    file: QUALIFICATION_FILE
  };
}

module.exports = {
  COMMON_INFORMATION,
  QUALIFICATION_STATES,
  QUALIFICATION_FILE,
  normalizeQualificationState,
  getQualificationView
};

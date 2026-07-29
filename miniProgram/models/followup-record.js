const FOLLOWUP_METHODS = [
  { id: 'phone', label: '电话', icon: 'phone-o' },
  { id: 'wechat', label: '微信', icon: 'wechat' },
  { id: 'in-person', label: '当面', icon: 'user-o' },
  { id: 'other', label: '其他', icon: 'apps-o' }
];

const FOLLOWUP_RESULTS = [
  { id: 'connected', label: '已沟通' },
  { id: 'waiting', label: '待回复' },
  { id: 'unanswered', label: '未接通' }
];

function formatFollowupDate(value) {
  const match = String(value || '').match(
    /^(\d{4})-(\d{2})-(\d{2})$/
  );

  if (!match) return '';
  return `${match[1]}年${Number(match[2])}月${Number(match[3])}日`;
}

function validateFollowupRecord(form) {
  const content = String(form.content || '').trim();

  if (!FOLLOWUP_METHODS.some((item) => item.id === form.method)) {
    return { valid: false, message: '请选择跟进方式' };
  }

  if (!FOLLOWUP_RESULTS.some((item) => item.id === form.result)) {
    return { valid: false, message: '请选择跟进结果' };
  }

  if (!content) {
    return { valid: false, message: '请填写跟进内容' };
  }

  if (form.reminderEnabled && (!form.reminderDate || !form.reminderTime)) {
    return { valid: false, message: '请完善下次跟进提醒' };
  }

  return {
    valid: true,
    value: {
      ...form,
      content
    }
  };
}

module.exports = {
  FOLLOWUP_METHODS,
  FOLLOWUP_RESULTS,
  formatFollowupDate,
  validateFollowupRecord
};

const RESULT_STATES = {
  matching: {
    state: 'matching',
    heroImage: '/assets/images/binding-result-matching.png',
    heroTitle: '客户信息已提交',
    heroDescription: '暂未获取儒泰用户ID，系统将持续匹配',
    heroMeta: '北京侧关联关系已记录'
  },
  bound: {
    state: 'bound',
    heroImage: '/assets/images/binding-result-bound.png',
    heroTitle: '该客户已绑定',
    heroDescription: '系统检测到该客户已存在有效归属关系',
    heroMeta: ''
  },
  failed: {
    state: 'failed',
    heroImage: '/assets/images/binding-result-failed.png',
    heroTitle: '暂未匹配到儒泰用户',
    heroDescription: '请核对客户信息后再次提交',
    heroMeta: ''
  }
};

function normalizeResultState(state) {
  return RESULT_STATES[state] ? state : 'matching';
}

function getResultStateForRecord(record) {
  if (!record) return 'matching';
  if (record.status === 'bound') return 'bound';
  if (record.status === 'processing') return 'failed';
  return 'matching';
}

function getBindingResultViewModel(state) {
  return { ...RESULT_STATES[normalizeResultState(state)] };
}

function adaptBindingResult(payload = {}) {
  const state = payload.status === 'bound' ? 'bound' : payload.status === 'failed' ? 'failed' : 'matching'
  return { requestId: String(payload.requestId || ''), state, statusLabel: String(payload.statusLabel || '') }
}

module.exports = {
  RESULT_STATES,
  normalizeResultState,
  getResultStateForRecord,
  getBindingResultViewModel,
  adaptBindingResult
};

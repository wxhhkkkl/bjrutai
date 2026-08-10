const DEFAULT_API_BASES = Object.freeze({
  develop: 'http://192.168.110.24:8000',
  trial: '',
  release: ''
})

function normalizeEnvVersion(value) {
  return value === 'develop' || value === 'trial' || value === 'release'
    ? value
    : 'release'
}

function normalizeBase(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function resolveEnvironment(options = {}) {
  const envVersion = normalizeEnvVersion(options.envVersion)
  const apiBases = Object.assign({}, DEFAULT_API_BASES, options.apiBases)
  const apiBase = normalizeBase(apiBases[envVersion])

  if (envVersion !== 'develop' && !/^https:\/\//i.test(apiBase)) {
    throw new Error(`${envVersion} 环境必须配置 HTTPS API 地址`)
  }

  return {
    envVersion,
    apiBase,
    useMock: envVersion === 'develop' && options.requestedMock === true
  }
}

function detectEnvVersion() {
  if (typeof wx === 'undefined' || !wx.getAccountInfoSync) return 'develop'

  try {
    const account = wx.getAccountInfoSync() || {}
    return account.miniProgram && account.miniProgram.envVersion
      ? account.miniProgram.envVersion
      : 'develop'
  } catch (error) {
    return 'develop'
  }
}

function getRuntimeEnvironment(options = {}) {
  let requestedMock = options.requestedMock === true

  if (options.requestedMock === undefined
    && typeof wx !== 'undefined'
    && wx.getStorageSync) {
    requestedMock = wx.getStorageSync('lutai_dev_use_mock') === true
  }

  return resolveEnvironment({
    envVersion: options.envVersion || detectEnvVersion(),
    apiBases: options.apiBases,
    requestedMock
  })
}

module.exports = {
  DEFAULT_API_BASES,
  normalizeEnvVersion,
  resolveEnvironment,
  getRuntimeEnvironment
}

const DEFAULT_API_BASES = Object.freeze({
  // Keep local mini-program requests aligned with the LuTai backend dev server.
  develop: 'http://127.0.0.1:8000',
  trial: 'https://bjrutai.com',
  release: 'https://bjrutai.com'
})
const DEV_API_BASE_KEY = 'lutai_dev_api_base'

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

function readDevelopmentApiBase() {
  if (typeof wx === 'undefined' || !wx.getStorageSync) return ''

  try {
    return normalizeBase(wx.getStorageSync(DEV_API_BASE_KEY))
  } catch (error) {
    return ''
  }
}

function getRuntimeEnvironment(options = {}) {
  let requestedMock = options.requestedMock === true

  if (options.requestedMock === undefined
    && typeof wx !== 'undefined'
    && wx.getStorageSync) {
    requestedMock = wx.getStorageSync('lutai_dev_use_mock') === true
  }

  const envVersion = options.envVersion || detectEnvVersion()
  const apiBases = Object.assign({}, options.apiBases)
  if (envVersion === 'develop' && !Object.prototype.hasOwnProperty.call(apiBases, 'develop')) {
    const developmentApiBase = readDevelopmentApiBase()
    if (developmentApiBase) apiBases.develop = developmentApiBase
  }

  return resolveEnvironment({
    envVersion,
    apiBases,
    requestedMock
  })
}

module.exports = {
  DEFAULT_API_BASES,
  DEV_API_BASE_KEY,
  normalizeEnvVersion,
  resolveEnvironment,
  getRuntimeEnvironment
}

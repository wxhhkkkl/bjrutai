const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '../..')

function harness() {
  let now = 1000000000
  let session = {}
  let token = ''
  let getError
  let claimError
  let confirm = true
  let resolveModal
  let holdModal = false
  const storage = new Map()
  const calls = { info: [], claim: [], modal: [], toast: [], navigation: [] }
  const wx = {
    getStorageSync: (key) => storage.get(key),
    setStorageSync: (key, value) => storage.set(key, value),
    removeStorageSync: (key) => storage.delete(key),
    showModal(options) {
      calls.modal.push(options)
      resolveModal = () => options.success({ confirm })
      if (!holdModal) resolveModal()
    },
    showToast: (value) => calls.toast.push(value),
    switchTab: (value) => calls.navigation.push(value.url),
    redirectTo: (value) => calls.navigation.push(value.url),
    reLaunch: (value) => calls.navigation.push(value.url),
    navigateBack: () => calls.navigation.push('back'),
    login: ({ success }) => success({ code: 'wechat-code' })
  }
  const sessionService = {
    getCurrentSession: () => session,
    getAccessToken: () => token,
    getEntry: () => ({ type: 'switchTab', url: '/pages/home/index' })
  }
  const binding = {
    async getCodeInfo(refToken) {
      calls.info.push(refToken)
      if (getError) throw getError
      return { distributorName: '测试顾问' }
    },
    async claimWithSession(refToken) {
      calls.claim.push(refToken)
      if (claimError) throw claimError
      return { bindingStatus: 'bound' }
    },
    async claimCustomer() { return { session: {} } }
  }
  function loadService() {
    const context = {
      module: { exports: {} }, wx, Date: { now: () => now },
      require(name) {
        if (name === './session-service') return sessionService
        if (name === './customer-binding-code-service') return binding
        throw Error(name)
      }
    }
    vm.runInNewContext(fs.readFileSync(path.join(root, 'services/pending-binding-service.js'), 'utf8'), context)
    return context.module.exports
  }
  let pending = loadService()
  function page(file) {
    let definition
    const context = {
      Page(value) { definition = value }, wx, setTimeout, clearTimeout,
      getCurrentPages: () => [{}, {}],
      require(name) {
        if (name.endsWith('pending-binding-service')) return pending
        if (name.endsWith('customer-binding-code-service')) return binding
        if (name.endsWith('session-service')) return sessionService
        if (name.endsWith('auth-service')) return {
          async establishSession() {
            session = { userId: 'patient-1' }; token = 'access'
            return { session }
          }
        }
        if (name.endsWith('navigation-service')) return { updateTabBar() {} }
        if (name.includes('models/')) return require(path.resolve(path.dirname(path.join(root, file)), name))
        if (name.endsWith('-service')) return {}
        throw Error(name)
      }
    }
    vm.runInNewContext(fs.readFileSync(path.join(root, file), 'utf8'), context)
    return { ...definition, data: { ...definition.data }, setData(value) { Object.assign(this.data, value) } }
  }
  return {
    calls, binding, storage, page,
    get pending() { return pending },
    login(value = { userId: 'patient-1' }) { session = value; token = 'access' },
    logout() { session = {}; token = '' },
    restart() { pending = loadService() },
    advance(ms) { now += ms },
    infoError(value) { getError = value },
    claimError(value) { claimError = value },
    confirm(value) { confirm = value },
    holdModal() { holdModal = true },
    resolveModal() { resolveModal() }
  }
}

const tick = () => new Promise((resolve) => setImmediate(resolve))

test('scan → leave before validation → restart → login from my tab → confirm binds and preserves return target', async () => {
  const h = harness()
  const scan = h.page('pages/patient-binding/index.js')
  scan.onLoad({ scene: 'test-token' })
  scan.onUnload()
  await tick()
  assert.equal(h.pending.getPendingBinding().refToken, 'test-token')
  assert.equal(h.calls.claim.length, 0)
  h.restart()
  const login = h.page('pages/auth/login/index.js')
  login.onLoad({ from: 'profile' })
  await login.completeLogin({})
  assert.deepEqual(h.calls.claim, ['test-token'])
  assert.match(h.calls.modal[0].content, /测试顾问.*授权使用登录手机号/)
  assert.equal(h.pending.getPendingBinding(), null)
  assert.deepEqual(h.calls.navigation, ['/pages/profile/index'])
})

test('logged-in visitor returning home resumes a scanned source', async () => {
  const h = harness()
  await h.pending.loadScannedCode('home-token')
  h.login()
  const home = h.page('pages/home/index.js')
  for (const name of ['loadArticles', 'loadAboutArticle', 'loadWellnessArticle', 'loadWomenArticle', 'loadBanners']) home[name] = () => {}
  home.onShow()
  await tick()
  assert.deepEqual(h.calls.claim, ['home-token'])
})

test('no source and guest session do not show confirmation or bind', async () => {
  const h = harness()
  h.login()
  await h.pending.resumePendingBinding()
  h.pending.savePendingBinding('source')
  h.logout()
  await h.pending.resumePendingBinding()
  assert.equal(h.calls.modal.length, 0)
  assert.equal(h.calls.claim.length, 0)
  assert.equal(h.pending.getPendingBinding().refToken, 'source')
})

test('declining clears the source and login still returns to the article', async () => {
  const h = harness()
  h.pending.savePendingBinding('source')
  h.confirm(false)
  const login = h.page('pages/auth/login/index.js')
  login.onLoad({ from: 'comment', articleId: '12' })
  await login.completeLogin({})
  await h.pending.resumePendingBinding()
  assert.equal(h.pending.getPendingBinding(), null)
  assert.equal(h.calls.claim.length, 0)
  assert.equal(h.calls.modal.length, 1)
  assert.deepEqual(h.calls.navigation, ['back'])
})

test('concurrent login/home triggers share one modal and one request', async () => {
  const h = harness()
  h.pending.savePendingBinding('source'); h.login(); h.holdModal()
  const first = h.pending.resumePendingBinding()
  const second = h.pending.resumePendingBinding()
  await tick()
  assert.equal(first, second)
  assert.equal(h.calls.modal.length, 1)
  h.resolveModal()
  await Promise.all([first, second])
  assert.deepEqual(h.calls.claim, ['source'])
})

test('network failure keeps source, avoids immediate repeat, and retries after 60 seconds', async () => {
  const h = harness()
  h.pending.savePendingBinding('source'); h.login()
  h.claimError({ kind: 'NETWORK' })
  await h.pending.resumePendingBinding()
  assert.equal(h.pending.getPendingBinding().refToken, 'source')
  await h.pending.resumePendingBinding()
  assert.equal(h.calls.modal.length, 1)
  h.advance(60000); h.claimError(null)
  await h.pending.resumePendingBinding()
  assert.equal(h.calls.claim.length, 2)
  assert.equal(h.pending.getPendingBinding(), null)
})

for (const error of [{ kind: 'NOT_FOUND' }, { kind: 'VALIDATION' }, { kind: 'FORBIDDEN' }, { code: 40023 }, { code: 40024 }]) {
  test(`terminal binding failure clears source (${error.kind || error.code})`, async () => {
    const h = harness()
    h.pending.savePendingBinding('source'); h.login(); h.claimError(error)
    await h.pending.resumePendingBinding()
    assert.equal(h.pending.getPendingBinding(), null)
  })
}

test('invalid code stops before confirmation; business member does not attempt claim', async () => {
  const h = harness()
  h.pending.savePendingBinding('source'); h.login(); h.infoError({ kind: 'NOT_FOUND' })
  await h.pending.resumePendingBinding()
  assert.equal(h.calls.modal.length, 0)
  assert.equal(h.pending.getPendingBinding(), null)
  h.pending.savePendingBinding('new-source'); h.login({ userId: 'staff', hasBusinessMembership: true })
  await h.pending.resumePendingBinding()
  assert.equal(h.calls.claim.length, 0)
  assert.equal(h.pending.getPendingBinding(), null)
})

test('new valid scan replaces old source, invalid scan does not replace it, and 7-day expiry clears it', async () => {
  const h = harness()
  await h.pending.loadScannedCode('a')
  await h.pending.loadScannedCode('b')
  h.infoError({ kind: 'NOT_FOUND' })
  await assert.rejects(h.pending.loadScannedCode('invalid'))
  assert.equal(h.pending.getPendingBinding().refToken, 'b')
  h.advance(7 * 24 * 60 * 60 * 1000)
  assert.equal(h.pending.getPendingBinding(), null)
})

test('late validation and late claim cannot overwrite or clear a newer scanned source', async () => {
  const h = harness()
  let resolveOld
  const get = h.binding.getCodeInfo
  h.binding.getCodeInfo = (token) => token === 'old' ? new Promise((resolve) => { resolveOld = resolve }) : get(token)
  const old = h.pending.loadScannedCode('old')
  await h.pending.loadScannedCode('new')
  resolveOld({}); await old
  assert.equal(h.pending.getPendingBinding().refToken, 'new')
  let resolveClaim
  h.binding.claimWithSession = () => new Promise((resolve) => { resolveClaim = resolve })
  h.login()
  const claim = h.pending.resumePendingBinding()
  await tick()
  await h.pending.loadScannedCode('newer')
  resolveClaim({}); await claim
  assert.equal(h.pending.getPendingBinding().refToken, 'newer')
})

test('account changes while confirming prevent claim on another account', async () => {
  const h = harness()
  h.pending.savePendingBinding('source'); h.login(); h.holdModal()
  const work = h.pending.resumePendingBinding()
  await tick()
  h.login({ userId: 'someone-else' }); h.resolveModal()
  await work
  assert.equal(h.calls.claim.length, 0)
})

test('original scan authorization clears saved source before returning home', async () => {
  const h = harness()
  const scan = h.page('pages/patient-binding/index.js')
  scan.onLoad({ refToken: 'direct-token' })
  await tick()
  await scan.submit({ detail: { code: 'phone-code' } })
  assert.equal(h.pending.getPendingBinding(), null)
  assert.equal(h.calls.modal.length, 0)
  assert.deepEqual(h.calls.navigation, ['/pages/home/index'])
})

test('API environment change clears pending source and invalidates a late scan response', async () => {
  const h = harness()
  h.storage.set('lutai_session_api_base', 'https://previous.example.test')
  h.pending.savePendingBinding('previous-token')
  let resolveInfo
  h.binding.getCodeInfo = () => new Promise((resolve) => { resolveInfo = resolve })
  const loading = h.pending.loadScannedCode('late-token')
  let app
  vm.runInNewContext(fs.readFileSync(path.join(root, 'app.js'), 'utf8'), {
    App(value) { app = value }, wx: {
      getStorageSync: (key) => h.storage.get(key),
      setStorageSync: (key, value) => h.storage.set(key, value)
    }, Date,
    require(name) {
      if (name.endsWith('/env')) return { getRuntimeEnvironment: () => ({ apiBase: 'https://current.example.test' }) }
      if (name.endsWith('pending-binding-service')) return h.pending
      if (name.endsWith('session-service')) return { clearAuthenticatedSession() {} }
      if (name.endsWith('auth-service')) return {}
      throw Error(name)
    }
  })
  app.onLaunch()
  assert.equal(h.pending.getPendingBinding(), null)
  resolveInfo({}); await loading
  assert.equal(h.pending.getPendingBinding(), null)
})

test('session claim service uses the authenticated endpoint with explicit consent and no phone credential', async () => {
  let sent
  const context = {
    module: { exports: {} },
    require() { return { request: (url, options) => { sent = { url, options }; return Promise.resolve({}) } } }
  }
  vm.runInNewContext(fs.readFileSync(path.join(root, 'services/customer-binding-code-service.js'), 'utf8'), context)
  await context.module.exports.claimWithSession('test/token')
  assert.equal(sent.url, '/api/v1/customer-binding-codes/test%2Ftoken/claim-session')
  assert.equal(sent.options.method, 'POST')
  assert.notEqual(sent.options.auth, false)
  assert.equal(JSON.stringify(sent.options.data), '{"consentConfirmed":true}')
})

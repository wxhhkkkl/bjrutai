const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const pagePath = path.resolve(__dirname, '../../pages/patient-binding/index.js')
const conflictMessage = '该手机号已是客户顾问账号，不能作为客户绑定'

function setup(error) {
  let definition
  let elapsed = 0
  let claimCount = 0
  let sessionCount = 0
  const timers = new Map()
  const navigation = []
  const toasts = []
  const context = {
    Page(value) { definition = value },
    require(name) {
      if (name.endsWith('customer-binding-code-service')) {
        return { async claimCustomer() { claimCount++; if (error) throw error; return { session: {} } } }
      }
      if (name.endsWith('auth-service')) {
        return { async establishSession() { sessionCount++ } }
      }
      if (name.endsWith('pending-binding-service')) {
        return { getPendingBinding() { return null }, clearPendingBinding() {} }
      }
      throw new Error(`Unexpected module: ${name}`)
    },
    wx: {
      login({ success }) { success({ code: 'wechat-code' }) },
      showToast(options) { toasts.push(options) },
      switchTab({ url }) { navigation.push(url) }
    },
    setTimeout(callback, delay) {
      const id = Symbol('timer')
      timers.set(id, { callback, at: elapsed + delay })
      return id
    },
    clearTimeout(id) { timers.delete(id) }
  }
  vm.runInNewContext(fs.readFileSync(pagePath, 'utf8'), context)
  const page = {
    ...definition,
    data: { ...definition.data, state: 'ready', refToken: 'test-token' },
    setData(patch) { Object.assign(this.data, patch) }
  }
  const submit = () => page.submit({ detail: { code: 'phone-code' } })
  return {
    page, submit, navigation, toasts,
    get claimCount() { return claimCount },
    get sessionCount() { return sessionCount },
    advance(ms) {
      elapsed += ms
      for (const [id, timer] of timers) {
        if (timer.at <= elapsed) { timers.delete(id); timer.callback() }
      }
    }
  }
}

test('staff identity conflict displays the complete message and returns home after exactly 3 seconds', async () => {
  const flow = setup({ code: 40024, message: conflictMessage })
  await flow.submit()
  assert.equal(flow.page.data.bindingErrorMessage, conflictMessage)
  assert.equal(flow.toasts.length, 0)
  assert.equal(flow.page.data.submitting, true)
  await flow.submit()
  assert.equal(flow.claimCount, 1)
  assert.equal(flow.sessionCount, 0)
  flow.advance(2999)
  assert.deepEqual(flow.navigation, [])
  flow.advance(1)
  assert.deepEqual(flow.navigation, ['/pages/home/index'])
})

test('unloading the binding page cancels the delayed navigation', async () => {
  const flow = setup({ code: 40024, message: conflictMessage })
  await flow.submit()
  flow.page.onUnload()
  flow.advance(3000)
  assert.deepEqual(flow.navigation, [])
})

test('a conflict response arriving after unload does not schedule navigation', async () => {
  const flow = setup({ code: 40024, message: conflictMessage })
  const pending = flow.submit()
  flow.page.onUnload()
  await pending
  flow.advance(3000)
  assert.deepEqual(flow.navigation, [])
})

test('other binding failures allow retry and do not return home', async () => {
  const flow = setup({ code: 40025, message: '当前客户已绑定其他客户顾问' })
  await flow.submit()
  assert.equal(flow.page.data.submitting, false)
  assert.equal(flow.toasts[0].title, '当前客户已绑定其他客户顾问')
  await flow.submit()
  assert.equal(flow.claimCount, 2)
  flow.advance(3000)
  assert.deepEqual(flow.navigation, [])
})

test('successful binding still establishes the session and enters home immediately', async () => {
  const flow = setup()
  await flow.submit()
  assert.equal(flow.sessionCount, 1)
  assert.deepEqual(flow.navigation, ['/pages/home/index'])
})

test('declining native phone authorization does not claim a customer or establish a session', async () => {
  const flow = setup()
  await flow.page.submit({ detail: { errMsg: 'getPhoneNumber:fail user deny' } })
  assert.equal(flow.claimCount, 0)
  assert.equal(flow.sessionCount, 0)
  assert.deepEqual(flow.navigation, [])
  assert.equal(flow.toasts[0].title, '需要授权手机号才能完成绑定')
})

test('identity conflict message uses a wrapping page element instead of a truncated toast', () => {
  const template = fs.readFileSync(path.join(path.dirname(pagePath), 'index.wxml'), 'utf8')
  const styles = fs.readFileSync(path.join(path.dirname(pagePath), 'index.wxss'), 'utf8')
  assert.match(template, /\{\{bindingErrorMessage\}\}/)
  assert.match(template, /3 秒后自动返回首页/)
  assert.match(styles, /\.scan-binding-notice[\s\S]*white-space:\s*normal/)
})

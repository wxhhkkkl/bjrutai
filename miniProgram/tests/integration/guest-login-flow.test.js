const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function stubModule(modulePath, exports, originals) {
  originals.set(modulePath, require.cache[modulePath])
  require.cache[modulePath] = { id: modulePath, filename: modulePath, loaded: true, exports }
}

function restoreModules(originals) {
  for (const [modulePath, original] of originals) {
    if (original) require.cache[modulePath] = original
    else delete require.cache[modulePath]
  }
}

test('guest sees home and my tabs, and my opens login', () => {
  const componentPath = path.resolve(__dirname, '../../custom-tab-bar/index.js')
  const sessionPath = path.resolve(__dirname, '../../services/session-service.js')
  const originals = new Map()
  const previousComponent = global.Component
  const previousWx = global.wx
  let definition
  const navigation = []

  stubModule(sessionPath, {
    getCurrentSession: () => ({ role: 'unknown', userId: '' }),
    getAccessToken: () => ''
  }, originals)
  originals.set(componentPath, require.cache[componentPath])
  delete require.cache[componentPath]
  global.Component = (value) => { definition = value }
  global.wx = {
    navigateTo({ url }) { navigation.push(['navigateTo', url]) },
    switchTab({ url }) { navigation.push(['switchTab', url]) }
  }

  try {
    require(componentPath)
    const component = {
      data: { ...definition.data },
      setData(patch) { this.data = { ...this.data, ...patch } }
    }
    definition.lifetimes.attached.call(component)
    assert.deepEqual(component.data.tabs.map((item) => item.id), ['home', 'profile'])
    definition.methods.switchTab.call(component, {
      currentTarget: { dataset: { item: component.data.tabs[1] } }
    })
    assert.deepEqual(navigation, [['navigateTo', '/pages/auth/login/index?from=profile']])
  } finally {
    restoreModules(originals)
    global.Component = previousComponent
    global.wx = previousWx
  }
})

test('login returns to the intended profile tab or article', async () => {
  const pagePath = path.resolve(__dirname, '../../pages/auth/login/index.js')
  const authPath = path.resolve(__dirname, '../../services/auth-service.js')
  const sessionPath = path.resolve(__dirname, '../../services/session-service.js')
  const originals = new Map()
  const previousPage = global.Page
  const previousWx = global.wx
  const previousGetCurrentPages = global.getCurrentPages
  let definition
  const navigation = []
  let established = { requiresWechatBinding: false, session: { userId: 'u1' } }
  let entry = { type: 'switchTab', url: '/pages/home/index' }

  stubModule(authPath, {
    establishSession: async () => established
  }, originals)
  stubModule(sessionPath, {
    getEntry: () => entry
  }, originals)
  originals.set(pagePath, require.cache[pagePath])
  delete require.cache[pagePath]
  global.Page = (value) => { definition = value }
  global.wx = {
    navigateBack({ delta }) { navigation.push(['navigateBack', delta]) },
    redirectTo({ url }) { navigation.push(['redirectTo', url]) },
    switchTab({ url }) { navigation.push(['switchTab', url]) }
  }
  global.getCurrentPages = () => [{}, {}]

  try {
    require(pagePath)
    const page = {
      ...definition,
      data: { ...definition.data },
      setData(patch) { this.data = { ...this.data, ...patch } }
    }
    page.onLoad({ from: 'profile' })
    await page.completeLogin({})
    assert.deepEqual(navigation.pop(), ['switchTab', '/pages/profile/index'])
    page.browseAsGuest()
    assert.deepEqual(navigation.pop(), ['switchTab', '/pages/home/index'])

    page.onLoad({ from: 'comment', articleId: '12' })
    await page.completeLogin({})
    assert.deepEqual(navigation.pop(), ['navigateBack', 1])

    page.browseAsGuest()
    assert.deepEqual(navigation.pop(), ['navigateBack', 1])

    established = { requiresWechatBinding: true, session: { userId: 'u1' } }
    await page.completeLogin({})
    assert.deepEqual(navigation.pop(), ['redirectTo', '/pages/auth/bind-wechat/index?from=comment&articleId=12'])

    established = { requiresWechatBinding: false, session: { userId: 'u1' } }
    entry = { type: 'reLaunch', url: '/pages/auth/profile-setup/index' }
    await page.completeLogin({})
    assert.deepEqual(navigation.pop(), ['redirectTo', '/pages/auth/profile-setup/index?from=comment&articleId=12'])
  } finally {
    restoreModules(originals)
    global.Page = previousPage
    global.wx = previousWx
    global.getCurrentPages = previousGetCurrentPages
  }
})

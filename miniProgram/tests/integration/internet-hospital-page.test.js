const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

const projectRoot = path.resolve(__dirname, '../..')
const pagePath = path.join(projectRoot, 'pages/internet-hospital/index.js')

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function loadPage({ accessToken = '', session = {}, reportEvent } = {}) {
  const originalPage = global.Page
  const originalWx = global.wx
  let definition
  const navigations = []
  const reported = []
  const services = {
    'navigation-service.js': { updateTabBar() {} },
    'session-service.js': {
      getAccessToken: () => accessToken,
      getCurrentSession: () => session
    },
    'hospital-service.js': {
      EVENTS: { ENTRY_TAP: 'entry_tap', QR_LONGPRESS: 'qr_longpress' },
      reportEvent:
        reportEvent ||
        ((event) => {
          reported.push(event)
          return Promise.resolve({ recorded: true })
        })
    }
  }
  const cached = Object.entries(services).map(([file, exports]) => {
    const fullPath = path.join(projectRoot, 'services', file)
    const previous = require.cache[fullPath]
    require.cache[fullPath] = {
      id: fullPath,
      filename: fullPath,
      loaded: true,
      exports
    }
    return [fullPath, previous]
  })
  const previousPage = require.cache[pagePath]
  delete require.cache[pagePath]
  global.Page = (value) => {
    definition = value
  }
  global.wx = {
    navigateTo(options) {
      navigations.push(options.url)
    },
    switchTab(options) {
      navigations.push(options.url)
    },
    showToast() {}
  }
  require(pagePath)
  return {
    definition,
    navigations,
    reported,
    restore() {
      global.Page = originalPage
      global.wx = originalWx
      if (previousPage) require.cache[pagePath] = previousPage
      else delete require.cache[pagePath]
      for (const [fullPath, previous] of cached) {
        if (previous) require.cache[fullPath] = previous
        else delete require.cache[fullPath]
      }
    }
  }
}

function instance(definition) {
  return {
    data: { ...definition.data },
    setData(next) {
      Object.assign(this.data, next)
    }
  }
}

test('guest tap leads to login without reporting or opening the popup', () => {
  const page = loadPage()
  try {
    const vm = instance(page.definition)
    page.definition.openHospitalQr.call(vm)

    assert.deepEqual(page.navigations, [
      '/pages/auth/login/index?from=internet-hospital'
    ])
    assert.equal(vm.data.qrVisible, false)
    assert.deepEqual(page.reported, [])
  } finally {
    page.restore()
  }
})

test('signed-in tap reports entry_tap and opens the popup', async () => {
  const page = loadPage({ accessToken: 'token', session: { userId: '9' } })
  try {
    const vm = instance(page.definition)
    page.definition.openHospitalQr.call(vm)
    await flush()

    assert.deepEqual(page.reported, ['entry_tap'])
    assert.equal(vm.data.qrVisible, true)
    assert.equal(vm.data.qrFailed, false)
    assert.deepEqual(page.navigations, [])
  } finally {
    page.restore()
  }
})

test('long press reports qr_longpress and a failed report stays silent', async () => {
  const reported = []
  const page = loadPage({
    accessToken: 'token',
    session: { userId: '9' },
    reportEvent: (event) => {
      reported.push(event)
      return Promise.reject(new Error('network'))
    }
  })
  try {
    const vm = instance(page.definition)
    page.definition.onQrLongPress.call(vm)
    await flush()

    assert.deepEqual(reported, ['qr_longpress'])
  } finally {
    page.restore()
  }
})

test('qr image failure switches the popup to the fallback text', () => {
  const page = loadPage()
  try {
    const vm = instance(page.definition)
    page.definition.onQrError.call(vm)
    assert.equal(vm.data.qrFailed, true)
  } finally {
    page.restore()
  }
})

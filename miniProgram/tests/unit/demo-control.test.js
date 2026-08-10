const test = require('node:test')
const assert = require('node:assert/strict')
const demo = require('../../mock/demo-control')

function withWx(envVersion, requestedMock, run) {
  const originalWx = global.wx
  const storage = { lutai_dev_use_mock: requestedMock }
  global.wx = {
    getAccountInfoSync() {
      return { miniProgram: { envVersion } }
    },
    getStorageSync(key) { return storage[key] },
    setStorageSync(key, value) { storage[key] = value },
    removeStorageSync(key) { delete storage[key] }
  }
  try {
    run()
  } finally {
    if (originalWx === undefined) delete global.wx
    else global.wx = originalWx
  }
}

test('demo control stores valid states only after explicit develop opt-in', () => {
  withWx('develop', true, () => {
    demo.resetDemoControl()
    demo.setPageViewState('home', 'empty')
    assert.equal(demo.getPageViewState('home'), 'empty')
    demo.setPageViewState('home', 'bad')
    assert.equal(demo.getPageViewState('home'), 'success')
  })
})

test('release ignores Demo storage and cannot expose a Demo identity', () => {
  withWx('release', true, () => {
    assert.equal(demo.isDemoEnabled(), false)
    assert.equal(demo.getDemoSession().userId, '')
    assert.equal(demo.getPageViewState('home'), 'recoverable-error')
  })
})

const { normalizeViewState } = require('../models/view-state')
const { sessions } = require('./foundation-fixtures')
const { getRuntimeEnvironment } = require('../config/env')
const SESSION_KEY = 'lutai_demo_session'
const VIEW_STATE_KEY = 'lutai_demo_view_state'
const memory = {}

function storageGet(key) { return typeof wx !== 'undefined' ? wx.getStorageSync(key) : memory[key] }
function storageSet(key, value) { if (typeof wx !== 'undefined') wx.setStorageSync(key, value); else memory[key] = value }
function storageRemove(key) { if (typeof wx !== 'undefined') wx.removeStorageSync(key); else delete memory[key] }

function isDemoEnabled() {
  try {
    return getRuntimeEnvironment().useMock === true
  } catch (error) {
    return false
  }
}

function getDemoSession() {
  if (!isDemoEnabled()) return sessions.unknown
  return storageGet(SESSION_KEY) || sessions.promoter
}
function setDemoSession(session) { if (isDemoEnabled()) storageSet(SESSION_KEY, session) }
function setScenario(name) { setDemoSession(sessions[name] || sessions.promoter) }
function getPageViewState(pageId) {
  if (!isDemoEnabled()) return 'recoverable-error'
  const states = storageGet(VIEW_STATE_KEY) || {}
  return normalizeViewState(states[pageId])
}
function setPageViewState(pageId, state) {
  if (!isDemoEnabled()) return
  const states = storageGet(VIEW_STATE_KEY) || {}
  states[pageId] = normalizeViewState(state)
  storageSet(VIEW_STATE_KEY, states)
}
function resetDemoControl() { storageRemove(SESSION_KEY); storageRemove(VIEW_STATE_KEY) }

module.exports = { SESSION_KEY, VIEW_STATE_KEY, isDemoEnabled, getDemoSession, setDemoSession, setScenario, getPageViewState, setPageViewState, resetDemoControl }

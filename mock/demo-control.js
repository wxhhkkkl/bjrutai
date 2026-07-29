const { normalizeViewState } = require('../models/view-state')
const { sessions } = require('./foundation-fixtures')
const SESSION_KEY = 'lutai_demo_session'
const VIEW_STATE_KEY = 'lutai_demo_view_state'
const memory = {}

function storageGet(key) { return typeof wx !== 'undefined' ? wx.getStorageSync(key) : memory[key] }
function storageSet(key, value) { if (typeof wx !== 'undefined') wx.setStorageSync(key, value); else memory[key] = value }
function storageRemove(key) { if (typeof wx !== 'undefined') wx.removeStorageSync(key); else delete memory[key] }

function getDemoSession() { return storageGet(SESSION_KEY) || sessions.promoter }
function setDemoSession(session) { storageSet(SESSION_KEY, session) }
function setScenario(name) { setDemoSession(sessions[name] || sessions.promoter) }
function getPageViewState(pageId) { const states = storageGet(VIEW_STATE_KEY) || {}; return normalizeViewState(states[pageId]) }
function setPageViewState(pageId, state) { const states = storageGet(VIEW_STATE_KEY) || {}; states[pageId] = normalizeViewState(state); storageSet(VIEW_STATE_KEY, states) }
function resetDemoControl() { storageRemove(SESSION_KEY); storageRemove(VIEW_STATE_KEY) }

module.exports = { SESSION_KEY, VIEW_STATE_KEY, getDemoSession, setDemoSession, setScenario, getPageViewState, setPageViewState, resetDemoControl }

const { TAB_ITEMS, ACTION_TARGETS } = require('../models/navigation')
const { hasCapability } = require('../models/collaborator')

function getAction(actionId) { return ACTION_TARGETS[actionId] || null }
function canOpen(actionId, session) {
  const action = getAction(actionId)
  if (!action) return false
  return hasCapability(session, action.capability)
}
function resolveActionPath(actionId, action, session) {
  return action.path
}

function openAction(actionId, session) {
  const action = getAction(actionId)
  if (!action || !canOpen(actionId, session)) return { ok: false, message: '当前账号暂不可使用此功能' }
  return {
    ok: true,
    url: resolveActionPath(actionId, action, session),
    title: action.title
  }
}
function updateTabBar(page, selected) { const bar = page.getTabBar && page.getTabBar(); if (bar) bar.setData({ selected }) }
module.exports = {
  TAB_ITEMS,
  getAction,
  canOpen,
  resolveActionPath,
  openAction,
  updateTabBar
}

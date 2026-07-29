const VIEW_STATES = ['loading', 'success', 'empty', 'recoverable-error', 'forbidden']

function isViewState(value) {
  return VIEW_STATES.indexOf(value) !== -1
}

function normalizeViewState(value) {
  return isViewState(value) ? value : 'success'
}

module.exports = { VIEW_STATES, isViewState, normalizeViewState }

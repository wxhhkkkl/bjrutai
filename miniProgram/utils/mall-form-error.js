function setMallFormError(page, message, { field = '', target = field } = {}) {
  page.setData({ stateMessage: message, focusField: '', errorTarget: '' }, () => {
    page.setData({
      focusField: field,
      errorTarget: target ? `mall-field-${target}` : ''
    })
  })
}

function clearMallFormError(page) {
  page.setData({ stateMessage: '', focusField: '', errorTarget: '' })
}

module.exports = { setMallFormError, clearMallFormError }

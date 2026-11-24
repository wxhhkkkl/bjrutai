const { request } = require('./request-service')
const { getAccessToken } = require('./session-service')

const EVENTS = Object.freeze({
  ENTRY_TAP: 'entry_tap',
  QR_LONGPRESS: 'qr_longpress'
})

const VALID_EVENTS = [EVENTS.ENTRY_TAP, EVENTS.QR_LONGPRESS]

function reportEvent(event) {
  if (!VALID_EVENTS.includes(event)) {
    return Promise.reject(new Error('不支持的事件类型'))
  }
  // Analytics must never clear the session: send the token as an optional
  // header with auth disabled, so an expired token becomes an anonymous event.
  const token = getAccessToken()
  return request('/api/v1/hospital/events', {
    method: 'POST',
    auth: false,
    header: token ? { Authorization: `Bearer ${token}` } : {},
    data: { event }
  })
}

module.exports = {
  EVENTS,
  reportEvent
}

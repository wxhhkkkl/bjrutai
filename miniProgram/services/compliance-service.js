const { request } = require('./request-service')
const getLatestAgreements = () => request('/api/v1/agreements/latest')
const getConsents = () => request('/api/v1/me/consents')
const recordConsent = (data) => request('/api/v1/consents', { method: 'POST', data })
const updatePrivacySettings = (data) => request('/api/v1/me/privacy-settings', { method: 'PUT', data })
module.exports = { getLatestAgreements, getConsents, recordConsent, updatePrivacySettings }

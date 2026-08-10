const { request } = require('./request-service')
const getUploadToken = (data) => request('/api/v1/feedback-files/upload-token', { method: 'POST', data })
const submitFeedback = (data) => request('/api/v1/feedbacks', { method: 'POST', data })
module.exports = { getUploadToken, submitFeedback }

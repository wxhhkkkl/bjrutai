const { request } = require('./request-service')
const { uploadImage } = require('./cos-upload')
const getUploadToken = (data) => request('/api/v1/feedback-files/upload-token', { method: 'POST', data })
const uploadFeedbackImage = (filePath, file = {}) => uploadImage(filePath, file, getUploadToken, '截图')
const submitFeedback = (data, idempotencyKey) => request('/api/v1/feedbacks', { method: 'POST', data, idempotencyKey })
module.exports = { getUploadToken, uploadFeedbackImage, submitFeedback }

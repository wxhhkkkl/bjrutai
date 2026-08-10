const { request } = require('./request-service')
const { uploadImage } = require('./cos-upload')
function getProfile() { return request('/api/v1/me/profile') }
function updateProfile(data) { return request('/api/v1/me/profile', { method: 'PUT', data }) }
function getAvatarUploadToken(data) { return request('/api/v1/me/avatar/upload-token', { method: 'POST', data }) }

async function uploadAvatar(filePath, file = {}) {
  return uploadImage(filePath, file, getAvatarUploadToken, '头像')
}

module.exports = { getProfile, updateProfile, getAvatarUploadToken, uploadAvatar }

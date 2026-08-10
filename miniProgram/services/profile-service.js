const { request } = require('./request-service')
function getProfile() { return request('/api/v1/me/profile') }
function updateProfile(data) { return request('/api/v1/me/profile', { method: 'PUT', data }) }
function getAvatarUploadToken(data) { return request('/api/v1/me/avatar/upload-token', { method: 'POST', data }) }

const MIME_TYPES = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', gif: 'image/gif', webp: 'image/webp' }

function imageMeta(filePath, file = {}) {
  const name = String(file.name || filePath || 'avatar.jpg').split('/').pop()
  const extension = (name.split('.').pop() || 'jpg').toLowerCase()
  return {
    fileName: name,
    contentType: MIME_TYPES[extension] || 'image/jpeg',
    fileSize: Number(file.size) > 0 ? Number(file.size) : 1
  }
}

function uploadToCos(uploadInfo, filePath, contentType) {
  return new Promise((resolve, reject) => {
    const fileSystem = wx.getFileSystemManager()
    fileSystem.readFile({
      filePath,
      success: ({ data }) => {
        wx.request({
          url: uploadInfo.uploadUrl,
          method: 'PUT',
          data,
          header: { 'Content-Type': contentType },
          timeout: 30000,
          success(response) {
            const statusCode = Number(response && response.statusCode) || 0
            if (statusCode >= 200 && statusCode < 300) resolve(uploadInfo)
            else reject(new Error('头像上传失败，请重试'))
          },
          fail: () => reject(new Error('头像上传失败，请检查网络后重试'))
        })
      },
      fail: () => reject(new Error('无法读取头像文件'))
    })
  })
}

async function uploadAvatar(filePath, file = {}) {
  const meta = imageMeta(filePath, file)
  const uploadInfo = await getAvatarUploadToken(meta)
  return uploadToCos(uploadInfo, filePath, meta.contentType)
}

module.exports = { getProfile, updateProfile, getAvatarUploadToken, uploadAvatar }

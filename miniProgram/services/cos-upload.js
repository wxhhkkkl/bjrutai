const MIME_TYPES = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', gif: 'image/gif', webp: 'image/webp' }

function imageMeta(filePath, file = {}) {
  const name = String(file.name || filePath || 'image.jpg').split('/').pop()
  const extension = (name.split('.').pop() || 'jpg').toLowerCase()
  return {
    fileName: name,
    contentType: MIME_TYPES[extension] || 'image/jpeg',
    fileSize: Number(file.size) > 0 ? Number(file.size) : 1,
  }
}

function uploadToCos(uploadInfo, filePath, contentType, label = '图片') {
  return new Promise((resolve, reject) => {
    wx.getFileSystemManager().readFile({
      filePath,
      success: ({ data }) => wx.request({
        url: uploadInfo.uploadUrl,
        method: 'PUT',
        data,
        header: { 'Content-Type': contentType },
        timeout: 30000,
        success(response) {
          const statusCode = Number(response && response.statusCode) || 0
          if (statusCode >= 200 && statusCode < 300) resolve(uploadInfo)
          else reject(new Error(`${label}上传失败，请重试`))
        },
        fail: () => reject(new Error(`${label}上传失败，请检查网络后重试`)),
      }),
      fail: () => reject(new Error(`无法读取${label}文件`)),
    })
  })
}

async function uploadImage(filePath, file, getToken, label = '图片') {
  const meta = imageMeta(filePath, file)
  const uploadInfo = await getToken(meta)
  return uploadToCos(uploadInfo, filePath, meta.contentType, label)
}

module.exports = { imageMeta, uploadToCos, uploadImage }

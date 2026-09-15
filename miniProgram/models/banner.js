function bannerFormatError(message) {
  const error = new Error(message)
  error.kind = 'MALFORMED'
  return error
}

function normalizeBannerId(value) {
  const text = String(value || '').trim()
  if (!/^\d+$/.test(text) || /^0*$/.test(text)) throw bannerFormatError('轮播图 ID 必须为正整数')
  return text.replace(/^0+/, '')
}

function normalizeArticleId(value) {
  const text = String(value || '').trim()
  if (!/^\d+$/.test(text) || /^0*$/.test(text)) throw bannerFormatError('轮播文章 ID 必须为正整数')
  return text.replace(/^0+/, '')
}

function optionalText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function adaptBanner(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw bannerFormatError('轮播图格式异常')
  }
  const imageUrl = optionalText(value.imageUrl)
  if (!/^https?:\/\//i.test(imageUrl)) throw bannerFormatError('轮播图图片地址无效')
  const actionType = value.actionType === 'article' ? 'article' : 'none'
  if (value.actionType !== 'article' && value.actionType !== 'none') {
    throw bannerFormatError('轮播图跳转类型无效')
  }
  return {
    bannerId: normalizeBannerId(value.bannerId),
    title: optionalText(value.title),
    imageUrl,
    actionType,
    articleId: actionType === 'article' ? normalizeArticleId(value.articleId) : '',
    sortOrder: Number.isInteger(value.sortOrder) && value.sortOrder >= 0 ? value.sortOrder : 0
  }
}

function adaptBannerList(payload) {
  if (!payload || typeof payload !== 'object' || !Array.isArray(payload.items)) {
    throw bannerFormatError('轮播图列表格式异常')
  }
  return payload.items.map(adaptBanner)
}

module.exports = {
  adaptBanner,
  adaptBannerList,
  normalizeBannerId
}

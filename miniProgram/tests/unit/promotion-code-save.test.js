const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadPage(wxMock) {
  const pagePath = path.resolve(__dirname, '../../pages/promotion-code/index.js')
  const originalPage = global.Page
  const originalWx = global.wx
  const originalGetApp = global.getApp
  const originalModule = require.cache[pagePath]
  let definition

  global.Page = (value) => { definition = value }
  global.wx = wxMock
  global.getApp = () => ({ globalData: { apiBase: 'https://bjrutai.com' } })
  delete require.cache[pagePath]
  require(pagePath)

  return {
    definition,
    restore() {
      delete require.cache[pagePath]
      if (originalModule) require.cache[pagePath] = originalModule
      global.Page = originalPage
      global.wx = originalWx
      global.getApp = originalGetApp
    }
  }
}

function createPage(definition) {
  return Object.assign({}, definition, {
    data: { profile: { qrImage: 'https://bjrutai.com/api/v1/customer-binding-codes/token/image' }, saving: false },
    setData(value) { this.data = Object.assign({}, this.data, value) }
  })
}

test('explains that the download domain must be configured when the platform blocks the URL', async () => {
  let modal
  const fixture = loadPage({
    downloadFile(options) { options.fail({ errMsg: 'downloadFile:fail url not in domain list' }) },
    showModal(options) { modal = options },
    showToast() {}
  })
  try {
    const page = createPage(fixture.definition)
    await page.savePromotionCode()

    assert.equal(modal.title, '图片下载域名未配置')
    assert.match(modal.content, /https:\/\/bjrutai\.com/)
    assert.equal(page.data.saving, false)
  } finally {
    fixture.restore()
  }
})

test('sharing uses brand covers while saving still downloads the original QR', async () => {
  let savedPath = ''
  let downloadedUrl = ''
  let toast
  const fixture = loadPage({
    downloadFile(options) { downloadedUrl = options.url; options.success({ statusCode: 200, tempFilePath: 'wxfile://tmp/qr.jpg' }) },
    saveImageToPhotosAlbum(options) { savedPath = options.filePath; options.success({}) },
    showToast(options) { toast = options }
  })
  try {
    const page = createPage(fixture.definition)
    page.data.profile.refToken = 'test-ref'
    const share = page.onShareAppMessage()
    assert.equal(share.title, '儒泰医联｜您的专属健康服务入口')
    assert.equal(share.path, '/pages/patient-binding/index?refToken=test-ref')
    assert.equal(share.imageUrl, '/assets/images/promotion-share-friend-v1.jpg')
    assert.deepEqual(page.onShareTimeline(), {
      title: share.title,
      query: 'refToken=test-ref',
      imageUrl: '/assets/images/promotion-share-timeline-v1.jpg'
    })
    await page.savePromotionCode()

    assert.equal(downloadedUrl, page.data.profile.qrImage)
    assert.notEqual(downloadedUrl, share.imageUrl)
    assert.equal(savedPath, 'wxfile://tmp/qr.jpg')
    assert.equal(toast.title, '已保存到相册')
    assert.equal(page.data.saving, false)
  } finally {
    fixture.restore()
  }
})

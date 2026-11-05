const { request } = require('./request-service')

const cache = Object.create(null)
let listLoadPromise = null
let listLoadedAt = 0

function pageKeyForRoute(route) {
  const normalized = String(route || '').replace(/^\/+/, '')
  if (normalized === 'pages/home/index') return 'home'
  if (normalized === 'pages/promotion-code/index') return 'promotion-code'
  return normalized.replace(/\//g, '_')
}

function loadShareConfig(pageKey) {
  return request(`/api/v1/share-configs/${encodeURIComponent(pageKey)}`, { auth: false })
    .then((config) => {
      if (config && config.pageKey) cache[pageKey] = config
      return config
    })
    .catch(() => cache[pageKey] || null)
}

function loadAllShareConfigs() {
  if (listLoadPromise) return listLoadPromise
  if (Date.now() - listLoadedAt < 60 * 1000) return Promise.resolve(Object.values(cache))
  listLoadPromise = request('/api/v1/share-configs', { auth: false })
    .then((configs) => {
      const items = Array.isArray(configs) ? configs : configs && configs.items || []
      Object.keys(cache).forEach((key) => { delete cache[key] })
      items.forEach((config) => {
        if (config && config.pageKey) cache[config.pageKey] = config
      })
      listLoadedAt = Date.now()
      return items
    })
    .catch(() => Object.values(cache))
    .finally(() => { listLoadPromise = null })
  return listLoadPromise
}

function getCachedShareConfig(pageKey) {
  return cache[pageKey] || null
}

function installGlobalShareHooks() {
  if (typeof Page !== 'function' || Page.__lutaiShareHooksInstalled) return
  const registerPage = Page
  const wrappedRegisterPage = function registerShareAwarePage(definition) {
    const page = definition || {}
    const originalOnLoad = page.onLoad
    const originalShare = page.onShareAppMessage
    const originalTimelineShare = page.onShareTimeline

    page.onLoad = function onLoadWithShareConfig(options) {
      const key = pageKeyForRoute(this.route)
      if (key) {
        this.__lutaiSharePageKey = key
        loadAllShareConfigs()
      }
      if (typeof originalOnLoad === 'function') return originalOnLoad.call(this, options)
      return undefined
    }

    page.onShareAppMessage = function shareWithConfiguredCard(options) {
      const result = typeof originalShare === 'function' ? originalShare.call(this, options) : null
      const config = getCachedShareConfig(this.__lutaiSharePageKey || pageKeyForRoute(this.route))
      if (!config) return result || {}
      return {
        ...(result || {}),
        title: config.friendTitle || result?.title,
        imageUrl: config.friendImageUrl || result?.imageUrl,
        path: result?.path || config.landingPath,
      }
    }

    if (typeof originalTimelineShare === 'function') {
      page.onShareTimeline = function shareTimelineWithConfiguredCard(options) {
        const result = originalTimelineShare.call(this, options)
        const config = getCachedShareConfig(this.__lutaiSharePageKey || pageKeyForRoute(this.route))
        if (!config || !config.timelineTitle || !config.timelineImageUrl) return result
        return {
          ...(result || {}),
          title: config.timelineTitle,
          imageUrl: config.timelineImageUrl,
        }
      }
    }

    return registerPage(page)
  }
  wrappedRegisterPage.__lutaiShareHooksInstalled = true
  Page = wrappedRegisterPage
}

module.exports = { loadShareConfig, loadAllShareConfigs, getCachedShareConfig, pageKeyForRoute, installGlobalShareHooks }

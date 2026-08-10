const { request } = require('./request-service')
function listNotifications(options = {}) { const data = {}; ['category', 'unreadOnly', 'cursor', 'pageSize'].forEach((key) => { if (options[key] !== undefined) data[key] = options[key] }); return request('/api/v1/notifications', { data: Object.keys(data).length ? data : undefined }) }
function markRead(id) { return request(`/api/v1/notifications/${encodeURIComponent(String(id))}/read`, { method: 'POST' }) }
function markAllRead() { return request('/api/v1/notifications/read-all', { method: 'POST' }) }
module.exports = { listNotifications, markRead, markAllRead }

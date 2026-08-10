const test = require('node:test')
const assert = require('node:assert/strict')
const { adaptNotifications, resolveNotificationTarget } = require('../../models/notification')

test('notification adapter formats dates and keeps only safe internal targets', () => {
  const result = adaptNotifications({
    items: [{ id: 1, category: 'binding', title: '绑定', summary: '状态更新', createdAt: '2026-08-10T01:20:59Z', isRead: false, target: '/pages/binding-records/index?filter=bound' }],
    unreadCount: 1,
    nextCursor: '2',
    hasMore: true
  })
  assert.equal(result.items[0].createdAt, '2026年8月10日 09:20')
  assert.equal(result.items[0].targetPath, '/pages/binding-records/index?filter=bound')
  assert.equal(resolveNotificationTarget('https://example.com'), '')
  assert.equal(resolveNotificationTarget('/pages/admin/index'), '')
})

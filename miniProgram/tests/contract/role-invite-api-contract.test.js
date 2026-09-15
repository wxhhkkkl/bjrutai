const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

const projectRoot = path.resolve(__dirname, '../..')

test('customer binding and staff invite services use separate endpoints', () => {
  const customer = require(path.join(projectRoot, 'services/customer-binding-code-service'))
  const staff = require(path.join(projectRoot, 'services/staff-invite-service'))

  assert.equal(typeof customer.getCodeInfo, 'function')
  assert.equal(typeof customer.claimCustomer, 'function')
  assert.equal(typeof staff.getMyInviteCode, 'function')
  assert.equal(typeof staff.joinOrganization, 'function')
})

test('app declares dedicated customer and staff scan pages', () => {
  const app = require(path.join(projectRoot, 'app.json'))
  assert.ok(app.pages.includes('pages/patient-binding/index'))
  assert.ok(app.pages.includes('pages/staff-join/index'))
  assert.ok(app.pages.includes('pages/staff-invite/index'))
})

test('staff invite image follows the active mini program API environment', () => {
  const staff = require(path.join(projectRoot, 'services/staff-invite-service'))
  const invite = {
    refToken: 'fresh-token',
    qrImageUrl: 'https://bjrutai.com/api/v1/staff-invite-codes/stale-token/image'
  }

  assert.equal(
    staff.resolveInviteImageUrl(invite, 'http://127.0.0.1:8000/'),
    'http://127.0.0.1:8000/api/v1/staff-invite-codes/fresh-token/image'
  )
  assert.equal(
    staff.formatInviteExpiry('2026-09-21T09:33:27'),
    '2026年9月21日 17:33'
  )
})

test('customer binding image and expiry follow the active mini program API environment', () => {
  const promotion = require(path.join(projectRoot, 'services/promotion-service'))

  assert.equal(
    promotion.resolveBindingImageUrl('binding-token', 'http://127.0.0.1:8000/'),
    'http://127.0.0.1:8000/api/v1/customer-binding-codes/binding-token/image'
  )
  assert.equal(
    promotion.formatPromotionExpiry('2026-09-21T09:33:27'),
    '2026年9月21日 17:33'
  )
})

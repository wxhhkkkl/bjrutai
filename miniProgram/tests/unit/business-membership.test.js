const test = require('node:test')
const assert = require('node:assert/strict')

const { getCollaboratorCapabilities } = require('../../models/collaborator')
const { getVisibleTabs } = require('../../models/navigation')
const { normalizeSession } = require('../../services/session-service')

test('personal account has no customer or consumption capability', () => {
  const personal = normalizeSession({
    userId: '1',
    role: 'personal',
    activationStatus: 'active',
    hasBusinessMembership: false
  })

  const capabilities = getCollaboratorCapabilities(personal)
  assert.equal(capabilities.customerBinding, false)
  assert.equal(capabilities.contribution, false)
  assert.deepEqual(getVisibleTabs(personal).map((item) => item.id), ['home', 'profile'])
})

test('business member sees customer and consumption tabs', () => {
  const member = normalizeSession({
    userId: '2',
    distributorId: '20',
    role: 'distributor',
    activationStatus: 'active',
    hasBusinessMembership: true,
    membershipStatus: 'active',
    orgStatus: 'active',
    orgRole: 'member'
  })

  assert.deepEqual(
    getVisibleTabs(member).map((item) => item.id),
    ['home', 'customers', 'contribution', 'profile']
  )
})

test('only organization admin can develop staff', () => {
  const base = {
    userId: '3',
    distributorId: '30',
    role: 'distributor',
    activationStatus: 'active',
    hasBusinessMembership: true,
    membershipStatus: 'active',
    orgStatus: 'active'
  }
  assert.equal(getCollaboratorCapabilities({ ...base, orgRole: 'member' }).staffInvite, false)
  assert.equal(getCollaboratorCapabilities({ ...base, orgRole: 'admin' }).staffInvite, true)
})


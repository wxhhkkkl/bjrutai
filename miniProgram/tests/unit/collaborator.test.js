const test = require('node:test');
const assert = require('node:assert/strict');
const {
  normalizeIdentityType,
  normalizeCollaboratorRole,
  getIdentityLabel,
  getCollaboratorCapabilities
} = require('../../models/collaborator');

test('legacy doctor and promoter sessions normalize to collaborators', () => {
  assert.equal(normalizeCollaboratorRole({ role: 'doctor' }), 'collaborator');
  assert.equal(normalizeCollaboratorRole({ role: 'promoter' }), 'collaborator');
  assert.equal(normalizeIdentityType({ role: 'doctor' }), 'doctor');
  assert.equal(normalizeIdentityType({ role: 'promoter' }), 'promoter');
});

test('professional identity only changes the display label', () => {
  assert.equal(
    getIdentityLabel({
      role: 'collaborator',
      identityType: 'doctor'
    }),
    '鲁泰医生'
  );
  assert.equal(
    getIdentityLabel({
      role: 'collaborator',
      identityType: 'promoter'
    }),
    '市场拓展人'
  );
});

test('qualified doctors and promoters receive the same capabilities', () => {
  const base = {
    role: 'collaborator',
    activationStatus: 'active',
    qualificationStatus: 'approved'
  };
  const doctor = getCollaboratorCapabilities({
    ...base,
    identityType: 'doctor'
  });
  const promoter = getCollaboratorCapabilities({
    ...base,
    identityType: 'promoter'
  });

  assert.deepEqual(doctor, promoter);
  assert.equal(doctor.promotion, true);
  assert.equal(doctor.contribution, true);
  assert.equal(doctor.customerBinding, true);
});

test('unqualified collaborators keep qualification access only', () => {
  const capabilities = getCollaboratorCapabilities({
    role: 'collaborator',
    identityType: 'doctor',
    activationStatus: 'active',
    qualificationStatus: 'reviewing'
  });

  assert.equal(capabilities.qualification, true);
  assert.equal(capabilities.promotion, false);
  assert.equal(capabilities.contribution, false);
});

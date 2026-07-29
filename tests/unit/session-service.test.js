const test = require('node:test'); const assert = require('node:assert/strict'); const { getEntry } = require('../../services/session-service')
test('inactive account enters qualification state', () => { assert.equal(getEntry({ userId:'x', role:'promoter', profileCompleted:true, activationStatus:'inactive' }).url, '/pages/qualification/status/index?state=inactive') })
test('unknown session enters login', () => { assert.equal(getEntry(null).url, '/pages/auth/login/index') })
test('doctor under review follows the same qualification gate', () => { assert.equal(getEntry({ userId:'d', role:'doctor', profileCompleted:true, activationStatus:'active', qualificationStatus:'reviewing' }).url, '/pages/qualification/status/index?state=reviewing') })

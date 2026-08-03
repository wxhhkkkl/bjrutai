const test = require('node:test'); const assert = require('node:assert/strict'); const { getEntry } = require('../../services/session-service')
test('inactive account enters placeholder state', () => { assert.equal(getEntry({ userId:'x', role:'promoter', profileCompleted:true, activationStatus:'inactive' }).url, '/pages/common/feature-placeholder/index?title=账号未激活') })
test('unknown session enters login', () => { assert.equal(getEntry(null).url, '/pages/auth/login/index') })
test('active account without personal qualification still enters home', () => { assert.equal(getEntry({ userId:'d', role:'doctor', profileCompleted:true, activationStatus:'active' }).url, '/pages/home/index') })

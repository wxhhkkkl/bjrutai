const test = require('node:test');
const assert = require('node:assert/strict');
const {
  formatFollowupDate,
  validateFollowupRecord
} = require('../../models/followup-record');

const validForm = {
  method: 'phone',
  result: 'connected',
  content: '确认客户随访时间与后续安排',
  reminderEnabled: true,
  reminderDate: '2026-07-23',
  reminderTime: '16:00'
};

test('followup date uses approved Chinese display format', () => {
  assert.equal(formatFollowupDate('2026-07-23'), '2026年7月23日');
  assert.equal(formatFollowupDate('invalid'), '');
});

test('followup validation requires content and reminder values', () => {
  assert.equal(validateFollowupRecord(validForm).valid, true);
  assert.equal(
    validateFollowupRecord({ ...validForm, content: '   ' }).valid,
    false
  );
  assert.equal(
    validateFollowupRecord({
      ...validForm,
      reminderTime: ''
    }).valid,
    false
  );
});

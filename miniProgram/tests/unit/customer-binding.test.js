const test = require('node:test');
const assert = require('node:assert/strict');
const {
  validateCustomerForm,
  maskPhone,
  maskIdCard,
  formatBindingTime
} = require('../../models/customer-binding');

test('customer binding validates required name and phone fields', () => {
  assert.equal(validateCustomerForm({}).field, 'name');
  assert.equal(
    validateCustomerForm({ name: '王女士', phone: '123' }).field,
    'phone'
  );
  assert.equal(validateCustomerForm({
    name: '王女士',
    phone: '13812349283'
  }).valid, true);
  assert.equal(validateCustomerForm({
    name: '王女士',
    phone: '13812349283',
    idCard: '123'
  }).field, 'idCard');
});

test('customer binding normalizes and masks submitted identity data', () => {
  const result = validateCustomerForm({
    name: ' 王女士 ',
    phone: '13812349283',
    idCard: '11010119900101123x'
  });

  assert.equal(result.valid, true);
  assert.equal(result.value.idCard, '11010119900101123X');
  assert.equal(maskPhone(result.value.phone), '138****9283');
  assert.equal(maskIdCard(result.value.idCard), '1101********123X');
});

test('binding time uses the approved display format', () => {
  const date = new Date(2025, 3, 20, 10, 30);

  assert.equal(formatBindingTime(date), '2025年4月20日 10:30');
});

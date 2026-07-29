const test = require('node:test');
const assert = require('node:assert/strict');
const {
  createCustomerEditForm,
  validateEditField,
  validateCustomerEditForm
} = require('../../models/customer-edit');

const customer = {
  name: '王女士',
  phone: '138****1028',
  idCard: '230***********4621',
  medicalAccount: '2301****6820',
  familyPhone: '186****3156'
};

test('customer edit form preserves approved masked values', () => {
  const form = createCustomerEditForm(customer);

  assert.equal(form.phone, '138****1028');
  assert.equal(validateCustomerEditForm(form).valid, true);
});

test('customer edit validates newly entered identity fields', () => {
  assert.equal(validateEditField('phone', '13800138000').valid, true);
  assert.equal(validateEditField('phone', '123').valid, false);
  assert.equal(
    validateEditField('idCard', '110101199001011234').valid,
    true
  );
});

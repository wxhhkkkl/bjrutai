const test = require('node:test');
const assert = require('node:assert/strict');
const {
  filterCustomers,
  sortCustomers
} = require('../../models/customer-list');

const customers = [
  { name: '王女士', phone: '138****1028', note: '最近服务：今日', status: '已绑定' },
  { name: '李先生', phone: '186****3681', note: '系统持续匹配', status: '待匹配' },
  { name: '刘女士', phone: '159****2650', note: '健康随访待完成', status: '待跟进' }
];

test('customer filters combine status and keyword', () => {
  assert.deepEqual(
    filterCustomers(customers, 'matching', '李'),
    [customers[1]]
  );
  assert.deepEqual(
    filterCustomers(customers, 'followup', '159'),
    [customers[2]]
  );
});

test('customer name sorting does not mutate the source list', () => {
  const sorted = sortCustomers(customers, 'name');

  assert.equal(customers[0].name, '王女士');
  assert.notEqual(sorted, customers);
  assert.deepEqual(
    sorted.map((customer) => customer.name),
    ['李先生', '刘女士', '王女士']
  );
});

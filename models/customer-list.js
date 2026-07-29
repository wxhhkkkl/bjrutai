function filterCustomers(list, selectedFilter, keyword) {
  const normalizedKeyword = keyword.trim().toLowerCase();

  return list.filter((customer) => {
    const matchesStatus = selectedFilter === 'all'
      || (selectedFilter === 'matching' && customer.status === '待匹配')
      || (selectedFilter === 'followup' && customer.status === '待跟进');
    const searchableText = [
      customer.name,
      customer.phone,
      customer.note
    ].join(' ').toLowerCase();

    return matchesStatus
      && (!normalizedKeyword || searchableText.includes(normalizedKeyword));
  });
}

function sortCustomers(list, sortMode) {
  const result = list.slice();

  if (sortMode === 'name') {
    result.sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'));
  }

  return result;
}

module.exports = {
  filterCustomers,
  sortCustomers
};

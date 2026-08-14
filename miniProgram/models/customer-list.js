function filterCustomers(list, selectedFilter, keyword) {
  const normalizedKeyword = keyword.trim().toLowerCase();

  return list.filter((customer) => {
    const matchesStatus = selectedFilter === 'all'
      || (selectedFilter === 'matching' && customer.status === '待匹配')
      || (selectedFilter === 'followup'
        && (customer.hasPendingFollowup === true || customer.status === '待跟进'));
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

const STATUS_LABELS = {
  bound: { label: '已绑定', tone: 'blue' },
  pending: { label: '待匹配', tone: 'orange' },
  unbound: { label: '待跟进', tone: 'green' }
}

const DEFAULT_AVATARS = {
  bound: '/assets/images/customer-avatar-blue.png',
  pending: '/assets/images/customer-avatar-purple.png',
  unbound: '/assets/images/customer-avatar-green.png',
  fallback: '/assets/images/customer-avatar-blue.png'
}

function adaptCustomerList(payload = {}) {
  const items = Array.isArray(payload.items) ? payload.items : []
  return {
    items: items.map((item) => {
      const status = STATUS_LABELS[item.bindingStatus] || { label: '处理中', tone: 'orange' }
      return {
        id: String(item.id || ''),
        name: String(item.name || '未命名客户'),
        phone: String(item.phoneMasked || item.phone || ''),
        note: String(item.note || ''),
        status: status.label,
        statusCode: String(item.bindingStatus || ''),
        hasPendingFollowup: item.hasPendingFollowup === true,
        tone: status.tone,
        avatar: String(item.avatar || DEFAULT_AVATARS[item.bindingStatus] || DEFAULT_AVATARS.fallback),
        promoterName: String(item.promoterName || ''),
        updatedAt: item.updatedAt || ''
      }
    }),
    nextCursor: payload.nextCursor ? String(payload.nextCursor) : '',
    hasMore: payload.hasMore === true
  }
}

module.exports = {
  filterCustomers,
  sortCustomers,
  adaptCustomerList
};

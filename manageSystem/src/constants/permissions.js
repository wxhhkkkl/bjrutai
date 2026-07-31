/**
 * RBAC Permission Definitions
 *
 * Each module groups one or more action permissions.
 * The full set of 22 permissions across 12 modules forms the seed data
 * for the "系统管理员" (System Admin) role.
 *
 * Format: { module, label, permissions: [{ key, label }] }
 * Permission key format: "{module}.{action}"  (e.g. "accounts.read")
 */

export const PERMISSION_MODULES = [
  {
    module: 'accounts',
    label: '账户管理',
    permissions: [
      { key: 'accounts.read', label: '查看管理员列表' },
      { key: 'accounts.write', label: '创建/编辑管理员' },
    ],
  },
  {
    module: 'roles',
    label: '角色管理',
    permissions: [
      { key: 'roles.read', label: '查看角色列表' },
      { key: 'roles.write', label: '创建/编辑/删除角色' },
    ],
  },
  {
    module: 'customers',
    label: '客户管理',
    permissions: [
      { key: 'customers.read', label: '查看客户列表及详情' },
      { key: 'customers.write', label: '编辑客户信息' },
    ],
  },
  {
    module: 'qualifications',
    label: '资质审核',
    permissions: [
      { key: 'qualifications.read', label: '查看资质申请' },
      { key: 'qualifications.write', label: '审核资质申请' },
    ],
  },
  {
    module: 'contributions',
    label: '业绩贡献',
    permissions: [
      { key: 'contributions.read', label: '查看业绩数据' },
    ],
  },
  {
    module: 'reports',
    label: '数据报表',
    permissions: [
      { key: 'reports.read', label: '查看报表' },
    ],
  },
  {
    module: 'articles',
    label: '文章管理',
    permissions: [
      { key: 'articles.read', label: '查看文章列表' },
      { key: 'articles.write', label: '创建/编辑/删除文章' },
    ],
  },
  {
    module: 'promotions',
    label: '推广码管理',
    permissions: [
      { key: 'promotions.read', label: '查看推广码' },
      { key: 'promotions.write', label: '创建/编辑推广码' },
    ],
  },
  {
    module: 'notifications',
    label: '消息通知',
    permissions: [
      { key: 'notifications.read', label: '查看通知' },
      { key: 'notifications.write', label: '发送通知' },
    ],
  },
  {
    module: 'hierarchy',
    label: '层级管理',
    permissions: [
      { key: 'hierarchy.read', label: '查看层级结构' },
      { key: 'hierarchy.write', label: '编辑层级结构' },
    ],
  },
  {
    module: 'sharing_rules',
    label: '分成规则',
    permissions: [
      { key: 'sharing_rules.read', label: '查看分成规则' },
      { key: 'sharing_rules.write', label: '编辑分成规则' },
    ],
  },
  {
    module: 'sync',
    label: '数据同步',
    permissions: [
      { key: 'sync.read', label: '查看同步状态' },
      { key: 'sync.write', label: '手动触发同步' },
    ],
  },
]

/**
 * Flatten all permission keys into a single array.
 * Used as seed data for the system admin role.
 */
export const ALL_PERMISSION_KEYS = PERMISSION_MODULES.flatMap((mod) =>
  mod.permissions.map((p) => p.key)
)

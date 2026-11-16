/**
 * RBAC Permission Definitions
 *
 * Each module groups one or more action permissions.
 * The full permission set across all modules forms the seed data
 * for the "系统管理员" (System Admin) role.
 *
 * Format: { module, label, permissions: [{ key, label }] }
 * Permission key format: "{module}.{action}"  (e.g. "accounts.read")
 */

export const PERMISSION_MODULES = [
  {
    module: 'mall_orders',
    label: '商城交易订单',
    permissions: [
      { key: 'mall.orders.read', label: '查看商城交易订单' },
      { key: 'mall.orders.write', label: '维护商城备注及未付关单' },
      { key: 'mall.shipments.write', label: '登记商城发货及更正运单' },
    ],
  },
  {
    module: 'mall_fulfillment',
    label: '商城履约资料（治理门禁）',
    permissions: [
      {
        key: 'mall.fulfillment.release',
        label: '申请读取指定订单履约资料（G-DATA未生效时仍拒绝）',
      },
    ],
  },
  {
    module: 'mall_invoices',
    label: '商城发票与红冲',
    permissions: [
      { key: 'mall.invoices.read', label: '查看商城发票申请与票据' },
      { key: 'mall.invoices.write', label: '办理商城开票、红冲和票据文件' },
      { key: 'mall.billing.release', label: '申请读取指定开票资料（受规范门禁控制）' },
    ],
  },
  {
    module: 'mall_aftersales',
    label: '商城售后与退款',
    permissions: [
      { key: 'mall.aftersales.read', label: '查看商城售后' },
      { key: 'mall.aftersales.review', label: '审核商城售后' },
      { key: 'mall.returns.receive', label: '验收商城退货' },
      { key: 'mall.refunds.read', label: '查看商城退款' },
      { key: 'mall.refunds.query', label: '查证商城渠道退款' },
      { key: 'mall.refunds.execute', label: '发起及重试商城原路退款' },
    ],
  },
  {
    module: 'mall_finance',
    label: '商城资金',
    permissions: [
      { key: 'mall.payments.read', label: '查看商城支付订单' },
      { key: 'mall.payments.query', label: '查证商城渠道支付' },
      { key: 'mall.finance.export', label: '导出商城支付/退款并读取本人导出文件' },
    ],
  },
  {
    module: 'mall_settings',
    label: '商城配送与交易设置',
    permissions: [
      { key: 'mall.settings.read', label: '查看商城配送与交易设置' },
      { key: 'mall.settings.write', label: '修改商城配送与交易设置' },
    ],
  },
  {
    module: 'mall_catalog',
    label: '商城商品与库存',
    permissions: [
      { key: 'mall.products.read', label: '查看商城商品及分类' },
      { key: 'mall.products.write', label: '维护商城商品及分类' },
      { key: 'mall.stock.read', label: '查看商城库存记录' },
      { key: 'mall.stock.write', label: '调整商城可售库存' },
      { key: 'mall.files.read', label: '查看授权商城文件' },
      { key: 'mall.files.write', label: '上传并核验授权商城文件' },
    ],
  },
  {
    module: 'mall_consumptions',
    label: '商城消费归属',
    permissions: [
      { key: 'mall.attribution.write', label: '核实未归属商城消费' },
    ],
  },
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
    module: 'org',
    label: '组织人员管理',
    permissions: [
      { key: 'org.read', label: '查看组织结构与资质' },
      { key: 'org.write', label: '编辑组织结构/资质' },
      { key: 'distributor.read', label: '查看分销员' },
      { key: 'distributor.write', label: '创建/编辑分销员' },
      { key: 'org_admin.write', label: '设置/撤销组织管理员' },
    ],
  },
  {
    module: 'contributions',
    label: '消费业绩',
    permissions: [
      { key: 'contributions.read', label: '查看业绩数据' },
      { key: 'contributions.write', label: '录入消费数据' },
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
    module: 'feedbacks',
    label: '意见与反馈',
    permissions: [
      { key: 'feedbacks.read', label: '查看全部用户反馈' },
      { key: 'feedbacks.write', label: '处理用户反馈' },
      { key: 'feedbacks.delete', label: '删除用户反馈' },
    ],
  },
  {
    module: 'comments',
    label: '评论管理',
    permissions: [
      { key: 'comments.read', label: '查看文章评论' },
      { key: 'comments.write', label: '审核/管理文章评论' },
    ],
  },
  {
    module: 'sharing_rules',
    label: '绩效规则',
    permissions: [
      { key: 'sharing_rules.read', label: '查看绩效规则' },
      { key: 'sharing_rules.write', label: '编辑绩效规则' },
    ],
  },
  {
    module: 'mini_program_shares',
    label: '小程序分享配置',
    permissions: [
      { key: 'mini_program_shares.read', label: '查看小程序分享配置' },
      { key: 'mini_program_shares.write', label: '编辑小程序分享配置' },
    ],
  },
  {
    module: 'performance',
    label: '绩效计算',
    permissions: [
      { key: 'performance.settle', label: '审核/导出月度核算' },
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

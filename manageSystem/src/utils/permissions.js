/**
 * Permission constants matching RBAC roles.
 * Admin: full access to all modules.
 * Finance: access to contributions, reports, accounts.
 * Ops: access to hierarchy, qualifications, customers, binding, sharing-rules, articles, notifications, promotions.
 */
export const ROLE_ADMIN = 'ADMIN'
export const ROLE_FINANCE = 'FINANCE'
export const ROLE_OPS = 'OPS'

export const PERMISSIONS = {
  // Dashboard
  DASHBOARD_VIEW: 'dashboard.view',

  // Hierarchy
  HIERARCHY_VIEW: 'hierarchy.view',
  HIERARCHY_MANAGE: 'hierarchy.manage',

  // Qualifications
  QUALIFICATION_VIEW: 'qualification.view',
  QUALIFICATION_REVIEW: 'qualification.review',
  QUALIFICATION_APPROVE: 'qualification.approve',

  // Customers
  CUSTOMER_VIEW: 'customer.view',
  CUSTOMER_MANAGE: 'customer.manage',
  CUSTOMER_BINDING_VIEW: 'customer.binding.view',
  CUSTOMER_BINDING_MANAGE: 'customer.binding.manage',

  // Contributions
  CONTRIBUTION_VIEW: 'contribution.view',
  CONTRIBUTION_EXPORT: 'contribution.export',

  // Sharing Rules
  SHARING_RULE_VIEW: 'sharing_rule.view',
  SHARING_RULE_MANAGE: 'sharing_rule.manage',

  // Reports
  REPORT_VIEW: 'report.view',
  REPORT_EXPORT: 'report.export',

  // Articles
  ARTICLE_VIEW: 'article.view',
  ARTICLE_MANAGE: 'article.manage',

  // Accounts
  ACCOUNT_VIEW: 'account.view',
  ACCOUNT_MANAGE: 'account.manage',

  // Notifications
  NOTIFICATION_VIEW: 'notification.view',
  NOTIFICATION_SEND: 'notification.send',

  // Promotions
  PROMOTION_VIEW: 'promotion.view',
  PROMOTION_MANAGE: 'promotion.manage',
}

/**
 * Default permission set per role.
 */
export const ROLE_PERMISSIONS = {
  [ROLE_ADMIN]: Object.values(PERMISSIONS),

  [ROLE_FINANCE]: [
    PERMISSIONS.DASHBOARD_VIEW,
    PERMISSIONS.CONTRIBUTION_VIEW,
    PERMISSIONS.CONTRIBUTION_EXPORT,
    PERMISSIONS.REPORT_VIEW,
    PERMISSIONS.REPORT_EXPORT,
    PERMISSIONS.ACCOUNT_VIEW,
    PERMISSIONS.ACCOUNT_MANAGE,
    PERMISSIONS.CUSTOMER_VIEW,
    PERMISSIONS.SHARING_RULE_VIEW,
  ],

  [ROLE_OPS]: [
    PERMISSIONS.DASHBOARD_VIEW,
    PERMISSIONS.HIERARCHY_VIEW,
    PERMISSIONS.HIERARCHY_MANAGE,
    PERMISSIONS.QUALIFICATION_VIEW,
    PERMISSIONS.QUALIFICATION_REVIEW,
    PERMISSIONS.QUALIFICATION_APPROVE,
    PERMISSIONS.CUSTOMER_VIEW,
    PERMISSIONS.CUSTOMER_MANAGE,
    PERMISSIONS.CUSTOMER_BINDING_VIEW,
    PERMISSIONS.CUSTOMER_BINDING_MANAGE,
    PERMISSIONS.SHARING_RULE_VIEW,
    PERMISSIONS.SHARING_RULE_MANAGE,
    PERMISSIONS.ARTICLE_VIEW,
    PERMISSIONS.ARTICLE_MANAGE,
    PERMISSIONS.NOTIFICATION_VIEW,
    PERMISSIONS.NOTIFICATION_SEND,
    PERMISSIONS.PROMOTION_VIEW,
    PERMISSIONS.PROMOTION_MANAGE,
  ],
}

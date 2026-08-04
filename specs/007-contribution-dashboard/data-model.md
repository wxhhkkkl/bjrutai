# Data Model: 业绩贡献页面增强

**Branch**: `007-contribution-dashboard` | **Date**: 2026-08-04
**Database**: MySQL 8.0 (InnoDB, utf8mb4)
**ORM**: SQLAlchemy 2.0+ (async)

**定位**: **无新增表**。排名/趋势/统计/绑定数均为对既有表的**实时聚合查询**。复用 `contribution_records`、`distributors`、`customers`、`organizations`。

---

## 1. 涉及的既有实体

| 表 | 用途 |
|---|---|
| `contribution_records` | 贡献值记录：`distributor_id`、`points`（字符串，如 "0.00"）、`category`、`status`、`occurred_at`、`settled_at` |
| `distributors` | 分销员归属：`id`、`org_id`、`org_role`（member/admin）、`status` |
| `customers` | 客户绑定：`distributor_id`、`binding_status`（bound/unbound/pending） |
| `organizations` | 组织树：`id`、`parent_id`、`name`、`level` |

**关键约束**:
- `points` 为字符串列 → 聚合需 `SUM(CAST(points AS DECIMAL(20,2)))`。
- 排名/统计按 `occurred_at`（贡献发生时间）而非 `created_at` 划分周期。

---

## 2. 聚合查询口径

### 2.1 统计（dashboard）
- 当月总业绩：`SUM(CAST(points))` where `occurred_at` in 当月
- 累计业绩：`SUM(CAST(points))`（全部）
- 组织数 / 人员数：`COUNT(organizations)` / `COUNT(distributors WHERE status='active')`
- 绑定用户数：`COUNT(customers WHERE binding_status='bound')`

### 2.2 月度趋势（近 N 月）
```sql
SELECT DATE_FORMAT(occurred_at, '%Y-%m') AS month, SUM(CAST(points AS DECIMAL(20,2))) AS points
FROM contribution_records
WHERE occurred_at >= 起点
GROUP BY month ORDER BY month
```

### 2.3 组织当月业绩排名
```sql
SELECT d.org_id, SUM(CAST(cr.points AS DECIMAL(20,2))) AS points
FROM contribution_records cr
JOIN distributors d ON cr.distributor_id = d.id
WHERE cr.occurred_at BETWEEN 当月起止
  AND d.org_id IN (子树 org_ids 或全部)      -- orgId 可选过滤
GROUP BY d.org_id ORDER BY points DESC
```

### 2.4 个人当月业绩排名
```sql
SELECT cr.distributor_id, SUM(CAST(cr.points AS DECIMAL(20,2))) AS points
FROM contribution_records cr
WHERE cr.occurred_at BETWEEN 当月起止
  AND cr.distributor_id IN (子树人员或全部)
GROUP BY cr.distributor_id ORDER BY points DESC
```

### 2.5 绑定数量排名
- **个人**：`SELECT distributor_id, COUNT(*) FROM customers WHERE binding_status='bound' GROUP BY distributor_id ORDER BY COUNT(*) DESC`
- **组织**：组织及全部下级人员名下绑定客户总数（按 `_collect_org_ids(subtree)` 聚合）

### 2.6 最新 30 条明细
```sql
SELECT * FROM contribution_records ORDER BY occurred_at DESC, id DESC LIMIT 30
```

---

## 3. 子树 org_ids 复用

`organization_service.get_subtree(db, org_id)` + `distributor_service._collect_org_ids(subtree)`（既有，同 005/006）。

---

## 4. 无迁移

本迭代不新增/变更表结构，无 Alembic 迁移。

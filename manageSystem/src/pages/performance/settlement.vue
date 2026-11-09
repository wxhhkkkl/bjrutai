<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">绩效计算</h2>
      <el-space>
        <el-select
          v-model="period"
          placeholder="选择可核算月份"
          style="width: 170px"
          filterable
          @change="loadAll"
        >
          <el-option
            v-for="p in settleablePeriods"
            :key="p"
            :value="p"
            :label="`${p}（可核算）`"
          />
        </el-select>
        <el-button
          v-if="canSettle && canSettleNow"
          type="primary"
          :loading="settling"
          @click="handleSettle"
        >
          发起核算
        </el-button>
        <el-button @click="loadAll">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
        </el-button>
      </el-space>
    </div>

    <div class="pr-layout">
      <!-- 左侧：组织结构树 -->
      <div class="tree-panel" v-loading="treeLoading">
        <div class="panel-title"><span>组织结构</span></div>
        <el-empty v-if="treeData.length === 0" description="暂无组织" :image-size="60" />
        <el-tree
          v-else
          ref="treeRef"
          :data="treeData"
          :props="{ label: 'name', children: 'children' }"
          node-key="orgId"
          default-expand-all
          highlight-current
          :expand-on-click-node="false"
          @node-click="handleSelect"
        >
          <template #default="{ data }">
            <div class="tree-node-content">
              <span class="node-name">{{ data.name }}</span>
              <span class="node-level">L{{ data.level }}</span>
            </div>
          </template>
        </el-tree>
      </div>

      <!-- 右侧：当月绩效估算 + 审核 -->
      <div class="detail-panel" v-loading="loading">
        <el-empty v-if="!selected" description="请在左侧选择组织查看当月绩效估算" :image-size="80" />
        <template v-else>
          <div class="org-header">
            <span class="org-title">{{ selected.name }}</span>
            <el-tag size="small" type="info" effect="plain">L{{ selected.level }}</el-tag>
            <div class="header-actions">
              <el-tag v-if="settlement" size="small" :type="statusType(settlement.status)">
                {{ statusLabel(settlement.status) }}
              </el-tag>
              <template v-if="canSettle && settlement && settlement.status === 'pending'">
                <el-button size="small" type="success" @click="handleReview">确认</el-button>
                <el-button size="small" type="warning" @click="rejectVisible = true">打回</el-button>
              </template>
              <el-button
                v-if="canSettle"
                size="small"
                :disabled="settlement && settlement.status === 'reviewed'"
                @click="handleRecompute"
              >重算</el-button>
              <el-button size="small" @click="handleExport">导出CSV</el-button>
            </div>
          </div>

          <div v-if="unconfigured.length" class="config-hint">
            未配置默认提成方式：{{ unconfigured.map((u) => u === 'intra_org' ? '组织内' : '组织管理').join('、') }}（未单独配置的人员无该部分提成）
          </div>

          <div class="performance-semantics">
            同一人员的旧账单与商城商品款先合并后命中原阶梯；正常绩效沿用旧提成金额字段。
            可兑现额读取净额结果，已抵扣负向调整不会重复扣减。
          </div>
          <el-table :data="estimateItems" size="small" empty-text="该组织暂无绩效估算">
            <el-table-column prop="name" label="姓名" width="140" />
            <el-table-column prop="ruleTypeLabel" label="提成类型" width="130" />
            <el-table-column label="合并消费基数">
              <template #default="{ row }">{{ fmtCent(row.baseCent) }}</template>
            </el-table-column>
            <el-table-column label="比例">
              <template #default="{ row }">{{ (row.ratio * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="正常绩效（原提成金额）">
              <template #default="{ row }">
                <span class="amount">{{ fmtCent(row.normalCommissionCent) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="调整金额">
              <template #default="{ row }">
                <span :class="row.confirmedAdjustmentCent < 0 ? 'amount-negative' : 'amount-adjustment'">
                  {{ fmtSignedCent(row.confirmedAdjustmentCent) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="已抵扣负向调整">
              <template #default="{ row }">
                <el-tooltip content="该金额已包含在调整金额中，不会再从可兑现额重复扣减" placement="top">
                  <span>{{ fmtCent(row.appliedDebtCent) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="可兑现">
              <template #default="{ row }">
                <span class="amount">{{ fmtCent(row.redeemableCent) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="待抵扣">
              <template #default="{ row }">{{ fmtCent(row.pendingDebtCent) }}</template>
            </el-table-column>
            <el-table-column label="积分（1元=1积分）" width="150">
              <template #default="{ row }">
                <span :class="row.pointsRedeemed ? 'points-redeemed' : 'points-balance'">
                  {{ fmtPoints(row.pointsBalance) }}
                </span>
                <el-tag v-if="row.pointsRedeemed" size="small" type="success" effect="plain" class="redeemed-tag">
                  已核销
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-tooltip
                  v-if="!row.pointsRedeemed && settlement?.status !== 'reviewed'"
                  content="仅已确认（冻结）的月份可以核销积分"
                  placement="top"
                >
                  <span>
                    <el-button size="small" type="success" disabled>积分核销</el-button>
                  </span>
                </el-tooltip>
                <el-button
                  v-else-if="!row.pointsRedeemed"
                  size="small"
                  type="success"
                  :disabled="!canSettle || Number(row.pointsBalance) <= 0"
                  :loading="redeemingKey === rowKey(row)"
                  @click="handleRedeemPoints(row)"
                >积分核销</el-button>
                <span v-else class="redeemed-action">已核销</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </div>

    <!-- 月度核算状态列表（含自动核算 pending 月份，供审核入口） -->
    <el-card class="status-card" shadow="never">
      <template #header><span>月度核算状态</span></template>
      <el-table :data="settlementItems" size="small" v-loading="statusLoading" empty-text="暂无核算批次">
        <el-table-column prop="period" label="月份" width="120" />
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rejectReason" label="打回原因" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="selectPeriod(row.period)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="status-card" shadow="never" data-test="performance-adjustments">
      <template #header>
        <div class="adjustment-header">
          <span>近期原期绩效差额</span>
          <span class="adjustment-note">保留原期证据及审核状态；未生成结果行的差额仍可追溯</span>
        </div>
      </template>
      <el-alert
        v-if="adjustmentsError"
        :title="adjustmentsError"
        type="error"
        show-icon
        :closable="false"
        class="adjustments-error"
      >
        <template #default>
          <el-button link type="primary" @click="loadAdjustments()">重试</el-button>
        </template>
      </el-alert>
      <el-table
        v-loading="adjustmentsLoading"
        :data="adjustments"
        size="small"
        empty-text="暂无绩效差额"
      >
        <el-table-column prop="originPeriod" label="原核算月" width="110" />
        <el-table-column prop="beneficiaryId" label="人员ID" width="100" />
        <el-table-column label="规则" width="120">
          <template #default="{ row }">{{ ruleTypeLabel(row.ruleType) }}</template>
        </el-table-column>
        <el-table-column label="原期结果行" min-width="150">
          <template #default="{ row }">
            <span v-if="row.originResultId">结果 {{ row.originResultId }}</span>
            <el-tag v-else size="small" type="warning">未生成结果行</el-tag>
            <span class="evidence-reference">证据 {{ row.originEvidenceId }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应调整" width="120" align="right">
          <template #default="{ row }">{{ fmtSignedCent(row.deltaCent) }}</template>
        </el-table-column>
        <el-table-column label="待结转" width="120" align="right">
          <template #default="{ row }">{{ fmtSignedCent(row.remainingCent) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="adjustmentStatusType(row.status)">
              {{ adjustmentStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="原期证据" width="120">
          <template #default="{ row }">{{ evidenceStatusLabel(row.evidenceStatus) }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="处理说明" min-width="170" show-overflow-tooltip />
      </el-table>
      <div v-if="adjustmentsNextCursor" class="adjustments-pagination">
        <el-button size="small" :loading="adjustmentsLoading" @click="loadMoreAdjustments">
          加载更多
        </el-button>
      </div>
    </el-card>

    <!-- 打回原因 -->
    <el-dialog v-model="rejectVisible" title="打回核算" width="440px">
      <el-input v-model="rejectReason" type="textarea" :rows="3" placeholder="请填写打回原因（必填）" />
      <template #footer>
        <el-button @click="rejectVisible = false">取消</el-button>
        <el-button type="warning" :loading="rejecting" @click="submitReject">确认打回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { orgApi } from '@/api/org'
import { performanceApi } from '@/api/performance'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const canSettle = computed(() => authStore.hasPermission('performance.settle'))

const now = new Date()
const period = ref(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)

const settleablePeriods = ref([])
const settling = ref(false)
const canSettleNow = computed(() => settleablePeriods.value.includes(period.value))

const treeLoading = ref(false)
const loading = ref(false)
const tree = ref([])
const treeData = computed(() => tree.value || [])
const treeRef = ref(null)
const selected = ref(null)

const estimate = ref({ intraOrg: [], orgManagement: [], unconfigured: [] })
const settlement = ref(null)

const settlementItems = ref([])
const statusLoading = ref(false)
const redeemingKey = ref('')
const adjustments = ref([])
const adjustmentsLoading = ref(false)
const adjustmentsError = ref('')
const adjustmentsNextCursor = ref(null)

const rejectVisible = ref(false)
const rejectReason = ref('')
const rejecting = ref(false)

const estimateItems = computed(() => {
  const normalize = (item, ruleType, ruleTypeLabel) => {
    const normal = Number(item.normalCommissionCent ?? item.commissionCent ?? 0)
    const adjustment = Number(item.confirmedAdjustmentCent ?? 0)
    return {
      ...item,
      ruleType,
      ruleTypeLabel,
      commissionCent: Number(item.commissionCent ?? normal),
      normalCommissionCent: normal,
      confirmedAdjustmentCent: adjustment,
      appliedDebtCent: Number(item.appliedDebtCent ?? 0),
      redeemableCent: Number(item.redeemableCent ?? Math.max(0, normal + adjustment)),
      pendingDebtCent: Number(item.pendingDebtCent ?? 0),
    }
  }
  const intra = (estimate.value.intraOrg || []).map((it) => normalize(it, 'intra_org', '组织内提成'))
  const mgmt = (estimate.value.orgManagement || []).map((it) => normalize(it, 'org_management', '组织管理提成'))
  return [...intra, ...mgmt]
})
const unconfigured = computed(() => estimate.value.unconfigured || [])

async function loadAdjustments({ cursor, append = false } = {}) {
  adjustmentsLoading.value = true
  adjustmentsError.value = ''
  try {
    const data = await performanceApi.listAdjustments({ cursor, pageSize: 20 })
    const items = Array.isArray(data?.items) ? data.items : []
    adjustments.value = append ? [...adjustments.value, ...items] : items
    adjustmentsNextCursor.value = data?.nextCursor || null
  } catch (error) {
    adjustmentsError.value = error.response?.data?.message || '绩效差额加载失败'
    if (!append) {
      adjustments.value = []
      adjustmentsNextCursor.value = null
    }
  } finally {
    adjustmentsLoading.value = false
  }
}

function loadMoreAdjustments() {
  if (adjustmentsNextCursor.value) {
    return loadAdjustments({ cursor: adjustmentsNextCursor.value, append: true })
  }
}

function flatten(n, acc = []) {
  acc.push(n)
  ;(n.children || []).forEach((c) => flatten(c, acc))
  return acc
}

async function loadSettleablePeriods() {
  try {
    const data = await performanceApi.settleablePeriods()
    settleablePeriods.value = data?.periods || []
  } catch {
    settleablePeriods.value = []
  }
}

async function loadSettlementStatus() {
  statusLoading.value = true
  try {
    const data = await performanceApi.settlements()
    settlementItems.value = data?.items || []
  } catch {
    settlementItems.value = []
  } finally {
    statusLoading.value = false
  }
}

function selectPeriod(p) {
  period.value = p
  loadAll()
}

async function loadAll() {
  await loadSettleablePeriods()
  await Promise.all([loadSettlementStatus(), loadAdjustments()])
  treeLoading.value = true
  try {
    const data = await orgApi.getTree()
    const roots = Array.isArray(data.tree) ? data.tree : (data.tree ? [data.tree] : [])
    tree.value = roots
    const flatAll = roots.flatMap((r) => flatten(r))
    if (selected.value) {
      const fresh = flatAll.find((o) => o.orgId === selected.value.orgId)
      handleSelect(fresh || flatAll[0] || null)
    } else if (flatAll.length > 0) {
      handleSelect(flatAll[0])
    }
    if (selected.value) treeRef.value?.setCurrentKey(selected.value.orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载组织树失败')
  } finally {
    treeLoading.value = false
  }
}

async function handleSelect(node) {
  selected.value = node
  if (node) await loadForOrg(node.orgId)
}

async function loadForOrg(orgId) {
  loading.value = true
  try {
    estimate.value = await performanceApi.estimates(period.value, orgId)
    const s = await performanceApi.settlements(period.value)
    settlement.value = (s.items || []).find((i) => i.period === period.value) || null
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载绩效估算失败')
  } finally {
    loading.value = false
  }
}

async function handleSettle() {
  try {
    await ElMessageBox.confirm(`确认对 ${period.value} 月发起核算？核算后该月进入待审核。`, '发起核算', {
      confirmButtonText: '核算', cancelButtonText: '取消', type: 'info',
    })
  } catch { return }
  settling.value = true
  try {
    await performanceApi.settle(period.value)
    ElMessage.success('核算成功，已进入待审核')
    await loadAll()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '发起核算失败')
  } finally {
    settling.value = false
  }
}

async function handleReview() {
  try {
    await ElMessageBox.confirm(`确认审核通过 ${period.value} 月的绩效核算？确认后将冻结该月数据。`, '审核确认', {
      confirmButtonText: '确认', cancelButtonText: '取消', type: 'info',
    })
  } catch { return }
  try {
    await performanceApi.review(period.value)
    ElMessage.success('已确认并冻结')
    await loadForOrg(selected.value.orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '确认失败')
  }
}

async function submitReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('请填写打回原因')
    return
  }
  rejecting.value = true
  try {
    await performanceApi.reject(period.value, rejectReason.value.trim())
    ElMessage.success('已打回')
    rejectVisible.value = false
    rejectReason.value = ''
    await loadForOrg(selected.value.orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '打回失败')
  } finally {
    rejecting.value = false
  }
}

async function handleRecompute() {
  try {
    await ElMessageBox.confirm(`确定重新核算 ${period.value} 月？`, '重新核算', {
      confirmButtonText: '重算', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  try {
    await performanceApi.recompute(period.value)
    ElMessage.success('重算完成')
    await loadForOrg(selected.value.orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '重算失败')
  }
}

async function handleRedeemPoints(row) {
  const key = rowKey(row)
  try {
    await ElMessageBox.confirm(
      `确认核销 ${row.name || '该员工'} 的 ${fmtPoints(row.pointsBalance)} 积分？核销后积分余额归零，提成金额保持不变。`,
      '积分核销',
      { confirmButtonText: '确认核销', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }

  redeemingKey.value = key
  try {
    await performanceApi.redeemPoints(period.value, row.distributorId, row.ruleType)
    ElMessage.success('积分核销成功，提成金额未变')
    await loadForOrg(selected.value.orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '积分核销失败')
  } finally {
    redeemingKey.value = ''
  }
}

function rowKey(row) {
  return `${row.distributorId}:${row.ruleType}`
}

async function handleExport() {
  try {
    const res = await performanceApi.export(period.value)
    const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `performance_${period.value}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '导出失败')
  }
}

function statusLabel(s) {
  return { pending: '待审核', reviewed: '已确认（冻结）', rejected: '已打回' }[s] || s
}
function statusType(s) {
  return { pending: 'warning', reviewed: 'success', rejected: 'danger' }[s] || 'info'
}
function adjustmentStatusLabel(s) {
  return {
    proposed: '待审核',
    manual_required: '待人工核实',
    reviewed: '已确认',
    rejected: '已拒绝',
  }[s] || '未知'
}
function adjustmentStatusType(s) {
  return { proposed: 'warning', manual_required: 'warning', reviewed: 'success', rejected: 'info' }[s] || 'info'
}
function evidenceStatusLabel(s) {
  return { complete: '证据完整', manual_required: '待补证/核实' }[s] || '未知'
}
function ruleTypeLabel(s) {
  return { intra_org: '组织内提成', org_management: '组织管理提成' }[s] || '未知规则'
}
function fmtCent(c) {
  return `¥${(Number(c || 0) / 100).toFixed(2)}`
}
function fmtSignedCent(c) {
  const amount = Number(c || 0)
  return `${amount < 0 ? '-' : ''}¥${(Math.abs(amount) / 100).toFixed(2)}`
}
function fmtPoints(points) {
  return Number(points || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

onMounted(loadAll)
</script>

<style scoped>
.pr-layout { display: flex; gap: 14px; align-items: flex-start; }
.tree-node-content { display: flex; align-items: center; gap: 8px; }
.node-level { color: var(--app-text-secondary); font-size: 12px; }

.org-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.org-title { font-size: 16px; font-weight: 600; color: #303133; }
.header-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.config-hint { color: #e6a23c; font-size: 12px; margin-bottom: 10px; }
.performance-semantics { margin: 0 0 10px; color: var(--app-text-secondary); font-size: 12px; line-height: 1.6; }
.amount { color: var(--el-color-primary); font-weight: 600; }
.amount-negative { color: var(--el-color-danger); font-weight: 600; }
.amount-adjustment { color: var(--el-color-success); font-weight: 600; }
.adjustment-header { display: flex; align-items: center; gap: 12px; }
.adjustment-note { color: var(--app-text-secondary); font-size: 12px; font-weight: 400; }
.adjustments-error { margin-bottom: 10px; }
.adjustments-pagination { display: flex; justify-content: flex-end; margin-top: 10px; }
.evidence-reference { margin-left: 8px; color: var(--app-text-secondary); font-size: 12px; }
.points-balance { color: #16845b; font-weight: 600; }
.points-redeemed { color: #909399; font-weight: 600; }
.redeemed-tag { margin-left: 6px; }
.redeemed-action { color: #67c23a; font-size: 12px; }
</style>

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
            未配置提成方式：{{ unconfigured.map((u) => u === 'intra_org' ? '组织内' : '组织管理').join('、') }}（相关人员无该部分提成）
          </div>

          <el-table :data="estimateItems" size="small" empty-text="该组织暂无绩效估算">
            <el-table-column prop="name" label="姓名" width="140" />
            <el-table-column prop="ruleTypeLabel" label="提成类型" width="130" />
            <el-table-column label="计算基数">
              <template #default="{ row }">{{ fmtCent(row.baseCent) }}</template>
            </el-table-column>
            <el-table-column label="比例">
              <template #default="{ row }">{{ (row.ratio * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="提成金额（预估）">
              <template #default="{ row }">
                <span class="amount">{{ fmtCent(row.commissionCent) }}</span>
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

const rejectVisible = ref(false)
const rejectReason = ref('')
const rejecting = ref(false)

const estimateItems = computed(() => {
  const intra = (estimate.value.intraOrg || []).map((it) => ({ ...it, ruleTypeLabel: '组织内提成' }))
  const mgmt = (estimate.value.orgManagement || []).map((it) => ({ ...it, ruleTypeLabel: '组织管理提成' }))
  return [...intra, ...mgmt]
})
const unconfigured = computed(() => estimate.value.unconfigured || [])

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
  await loadSettlementStatus()
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
function fmtCent(c) {
  return `¥${((c || 0) / 100).toFixed(2)}`
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
.amount { color: var(--el-color-primary); font-weight: 600; }
</style>

<template>
  <div class="sharing-rules-page">
    <div class="page-header">
      <h2 class="page-title">分成规则</h2>
      <div class="header-actions">
        <el-button type="primary" @click="openCreate">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>新增规则
        </el-button>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <div class="filter-left">
        <el-select
          v-model="filters.level"
          placeholder="选择组织层级"
          clearable
          style="width: 140px"
          @change="handleFilterChange"
        >
          <el-option
            v-for="n in orgLevels"
            :key="n"
            :label="'L' + n"
            :value="n"
          />
        </el-select>
        <el-select
          v-model="filters.status"
          placeholder="选择状态"
          clearable
          style="width: 140px"
          @change="handleFilterChange"
        >
          <el-option label="生效中" value="active" />
          <el-option label="已停用" value="inactive" />
          <el-option label="已过期" value="expired" />
        </el-select>
      </div>
      <div class="filter-right">
        <el-button @click="resetFilters">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>重置
        </el-button>
      </div>
    </div>

    <!-- Coefficient card -->
    <el-card class="coefficient-card" shadow="never">
      <div class="coefficient-row">
        <span class="coefficient-label">当前分成系数：</span>
        <span v-if="coefficientLoading" class="coefficient-value">加载中...</span>
        <span v-else class="coefficient-value">{{ store.coefficient ?? '未设置' }}</span>
        <el-button size="small" type="primary" plain @click="openCoefficientDialog">
          设置系数
        </el-button>
      </div>
    </el-card>

    <!-- Rules table -->
    <div class="table-container" v-loading="store.loading">
      <el-empty v-if="!store.loading && store.rules.length === 0" description="暂无分成规则" />
      <el-table v-else :data="store.rules" border stripe style="width: 100%">
        <el-table-column prop="level" label="层级" width="80" align="center" />
        <el-table-column label="规则类型" width="120">
          <template #default="{ row }">
            {{ store.getRuleTypeLabel(row.rule_type) }}
          </template>
        </el-table-column>
        <el-table-column label="计算基数" width="120">
          <template #default="{ row }">
            {{ store.getBaseLabel(row.base) }}
          </template>
        </el-table-column>
        <el-table-column label="数值" width="140">
          <template #default="{ row }">
            <span v-if="row.rule_type === 'fixed_ratio'">{{ (row.value * 100).toFixed(1) }}%</span>
            <span v-else-if="row.rule_type === 'fixed_amount'">￥{{ row.value }}</span>
            <span v-else>{{ row.value }}</span>
          </template>
        </el-table-column>
        <el-table-column label="生效时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.effective_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="store.getStatusType(row.status)" size="small">
              {{ store.getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEdit(row)">
              编辑
            </el-button>
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="danger"
              link
              @click="handleDeactivate(row)"
            >
              停用
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Rule form dialog -->
    <RuleForm
      v-model="showRuleForm"
      :is-edit="isEditing"
      :rule-data="currentRule"
      :org-levels="orgLevels"
      @success="onRuleFormSuccess"
    />

    <!-- Coefficient dialog -->
    <el-dialog
      v-model="showCoefficientDialog"
      title="设置分成系数"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="coefficientForm" label-width="100px">
        <el-form-item label="系数值">
          <el-input-number
            v-model="coefficientForm.value"
            :min="0"
            :max="10"
            :step="0.01"
            :precision="2"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCoefficientDialog = false">取消</el-button>
        <el-button type="primary" :loading="coefficientSubmitting" @click="handleUpdateCoefficient">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useSharingStore } from '@/stores/sharing'
import { orgApi } from '@/api/org'
import RuleForm from '@/components/sharing-rules/RuleForm.vue'

const store = useSharingStore()

// Distinct org-tree levels for the level filter / rule form (FR-005 arbitrary depth)
const orgLevels = ref([])
function collectLevels(nodes, acc = new Set()) {
  for (const node of nodes) {
    if (node.level != null) acc.add(node.level)
    if (node.children?.length) collectLevels(node.children, acc)
  }
  return acc
}
async function loadOrgLevels() {
  try {
    const payload = await orgApi.getTree()
    const items = Array.isArray(payload)
      ? payload
      : (Array.isArray(payload?.tree) ? payload.tree : (payload?.items || []))
    orgLevels.value = Array.from(collectLevels(items)).sort((a, b) => a - b)
  } catch {
    orgLevels.value = []
  }
}

const filters = reactive({
  level: null,
  status: null,
})

const showRuleForm = ref(false)
const isEditing = ref(false)
const currentRule = ref(null)

const showCoefficientDialog = ref(false)
const coefficientLoading = ref(false)
const coefficientSubmitting = ref(false)
const coefficientForm = reactive({ value: 0 })

function formatDate(isoStr) {
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function handleFilterChange() {
  store.fetchRules(filters)
}

function resetFilters() {
  filters.level = null
  filters.status = null
  store.fetchRules()
}

function openCreate() {
  isEditing.value = false
  currentRule.value = null
  showRuleForm.value = true
}

function openEdit(row) {
  isEditing.value = true
  currentRule.value = { ...row }
  showRuleForm.value = true
}

function onRuleFormSuccess() {
  currentRule.value = null
}

async function handleDeactivate(row) {
  try {
    await ElMessageBox.confirm(
      `确定要停用 L${row.level} 组织层级的「${store.getRuleTypeLabel(row.rule_type)}」规则吗？`,
      '确认停用',
      { confirmButtonText: '停用', cancelButtonText: '取消', type: 'warning' }
    )
    await store.deactivateRule(row.id)
  } catch {
    // user cancelled or error handled in store
  }
}

function openCoefficientDialog() {
  coefficientForm.value = store.coefficient ?? 0
  showCoefficientDialog.value = true
}

async function handleUpdateCoefficient() {
  coefficientSubmitting.value = true
  try {
    await store.updateCoefficient(coefficientForm.value)
    showCoefficientDialog.value = false
  } finally {
    coefficientSubmitting.value = false
  }
}

async function init() {
  coefficientLoading.value = true
  try {
    await Promise.all([store.fetchRules(), store.fetchCoefficient(), loadOrgLevels()])
  } finally {
    coefficientLoading.value = false
  }
}

onMounted(() => {
  init()
})
</script>

<style scoped>
.sharing-rules-page { padding: 10px 0; }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  padding: 12px 16px;
  border-radius: 4px;
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
}

.filter-left {
  display: flex;
  gap: 12px;
}

.coefficient-card {
  margin-bottom: 16px;
}

.coefficient-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.coefficient-label {
  font-size: 14px;
  color: #606266;
}

.coefficient-value {
  font-size: 18px;
  font-weight: 600;
  color: #409eff;
}

.table-container {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 16px;
  min-height: 200px;
}
</style>

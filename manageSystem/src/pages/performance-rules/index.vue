<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">绩效规则</h2>
      <el-button @click="loadAll"><el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新</el-button>
    </div>

    <div class="pr-layout">
      <!-- 左侧：组织结构树 -->
      <div class="tree-panel" v-loading="loading">
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

      <!-- 右侧：选中组织的绩效规则 -->
      <div class="detail-panel">
        <el-empty v-if="!selected" description="请在左侧选择组织查看其绩效规则" :image-size="80" />
        <template v-else>
          <div class="org-header">
            <span class="org-title">{{ selected.name }}</span>
            <el-tag size="small" type="info" effect="plain">L{{ selected.level }}</el-tag>
            <el-space wrap class="header-actions">
              <el-button size="small" @click="openHistory">变更历史</el-button>
            </el-space>
          </div>

          <!-- 组织内绩效提成 -->
          <el-card class="rule-card" shadow="never">
            <div class="rule-card__header">
              <span class="rule-title">组织内绩效提成</span>
              <el-tag :type="rules.intraOrg ? 'success' : 'info'" size="small">
                {{ rules.intraOrg ? '已配置' : '未配置' }}
              </el-tag>
              <span class="rule-desc">适用于本组织所有人员（按自身消费金额）</span>
              <el-button v-if="canWrite" size="small" type="primary" @click="openEditor('intra_org')">配置</el-button>
              <el-button
                v-if="canWrite"
                size="small"
                plain
                :disabled="!rules.intraOrg"
                :title="rules.intraOrg ? '' : '请先配置该绩效提成方式'"
                @click="applyToDesc('intra_org')"
              >应用到全部下级组织</el-button>
            </div>
            <div v-if="rules.intraOrg" class="tiers-display">
              <div v-for="(t, i) in rules.intraOrg.tiers" :key="i" class="tier-row">
                {{ fmtCent(t.minCent) }} ~ {{ t.maxCent === null ? '∞' : fmtCent(t.maxCent) }} → {{ (t.ratio * 100).toFixed(2) }}%
              </div>
            </div>
          </el-card>

          <!-- 组织管理绩效提成 -->
          <el-card class="rule-card" shadow="never">
            <div class="rule-card__header">
              <span class="rule-title">组织管理绩效提成</span>
              <el-tag :type="rules.orgManagement ? 'success' : 'info'" size="small">
                {{ rules.orgManagement ? '已配置' : '未配置' }}
              </el-tag>
              <span class="rule-desc">适用于组织管理员（基数=本组织及全部下级组织人员消费总额）</span>
              <el-button v-if="canWrite" size="small" type="primary" @click="openEditor('org_management')">配置</el-button>
              <el-button
                v-if="canWrite"
                size="small"
                plain
                :disabled="!rules.orgManagement"
                :title="rules.orgManagement ? '' : '请先配置该绩效提成方式'"
                @click="applyToDesc('org_management')"
              >应用到全部下级组织</el-button>
            </div>
            <div v-if="rules.orgManagement" class="tiers-display">
              <div v-for="(t, i) in rules.orgManagement.tiers" :key="i" class="tier-row">
                {{ fmtCent(t.minCent) }} ~ {{ t.maxCent === null ? '∞' : fmtCent(t.maxCent) }} → {{ (t.ratio * 100).toFixed(2) }}%
              </div>
            </div>
          </el-card>
        </template>
      </div>
    </div>

    <!-- 阶梯配置 -->
    <el-dialog :model-value="editorVisible" :title="editorType === 'intra_org' ? '配置组织内绩效提成' : '配置组织管理绩效提成'" width="520px" @close="closeEditor">
      <el-form size="small" label-width="80px">
        <div v-for="(t, i) in editorTiers" :key="i" class="tier-editor-row">
          <span class="tier-idx">阶梯 {{ i + 1 }}</span>
          <el-input-number v-model="t.minYuan" :min="0" :step="1000" :controls="false" placeholder="下限(元)" style="width: 120px" />
          <span>~</span>
          <el-input v-model.number="t.maxYuan" placeholder="上限(元)，空=∞" style="width: 150px" />
          <el-input-number v-model="t.ratioPercent" :min="0.01" :max="100" :step="1" :precision="2" style="width: 110px" />
          <span class="pct-suffix">%</span>
          <el-button link type="danger" @click="removeTier(i)">删除</el-button>
        </div>
        <div class="tier-actions">
          <el-button size="small" @click="addTier">添加阶梯</el-button>
          <span class="hint">金额单位：元；比率单位：%；末项上限留空表示上不封顶；阶梯需连续覆盖任意金额，不得有空隙或重叠</span>
        </div>
      </el-form>
      <template #footer>
        <el-button size="small" @click="closeEditor">取消</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="submitEditor">保存</el-button>
      </template>
    </el-dialog>

    <!-- 变更历史 -->
    <el-dialog v-model="historyVisible" title="变更历史" width="600px">
      <el-timeline v-if="historyItems.length">
        <el-timeline-item v-for="(h, i) in historyItems" :key="i" :timestamp="formatTime(h.createdAt)">
          <p style="margin: 0;">
            <el-tag size="small" :type="h.operationType === 'create' ? 'success' : (h.operationType === 'apply' ? 'warning' : 'info')" effect="plain">
              {{ operationLabel(h.operationType) }}
            </el-tag>
            <span style="margin-left: 8px;">{{ h.ruleType === 'intra_org' ? '组织内绩效提成' : '组织管理绩效提成' }}</span>
            <span class="muted">操作账户：{{ h.changedBy }}</span>
          </p>
          <div v-if="h.oldValue?.tiers && h.newValue?.tiers" class="muted history-diff">
            变更：{{ fmtTiers(h.oldValue.tiers) }} → {{ fmtTiers(h.newValue.tiers) }}
          </div>
          <div v-else-if="h.newValue?.tiers" class="muted history-diff">配置：{{ fmtTiers(h.newValue.tiers) }}</div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无变更记录" />
    </el-dialog>

  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { orgApi } from '@/api/org'
import { performanceApi } from '@/api/performance'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const canWrite = computed(() => authStore.hasPermission('sharing_rules.write'))

const loading = ref(false)
const saving = ref(false)
const tree = ref(null)
const treeRef = ref(null)
const selected = ref(null)
const rules = ref({ intraOrg: null, orgManagement: null, summary: {} })

const editorVisible = ref(false)
const editorType = ref('intra_org')
const editorTiers = ref([])

const historyVisible = ref(false)
const historyItems = ref([])

const treeData = computed(() => tree.value || [])

function flatten(n, acc = []) {
  acc.push(n)
  ;(n.children || []).forEach((c) => flatten(c, acc))
  return acc
}

async function loadAll() {
  loading.value = true
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
    loading.value = false
  }
}

async function handleSelect(node) {
  selected.value = node
  if (node) await loadRules(node.orgId)
}

async function loadRules(orgId) {
  try {
    rules.value = await performanceApi.getRules(orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载绩效规则失败')
  }
}

function openEditor(type) {
  editorType.value = type
  const current = type === 'intra_org' ? rules.value.intraOrg : rules.value.orgManagement
  editorTiers.value = (current?.tiers || [{ minCent: 0, maxCent: null, ratio: 0.05 }]).map((t) => ({
    minYuan: t.minCent / 100,
    maxYuan: t.maxCent != null ? t.maxCent / 100 : null,
    ratioPercent: Math.round(t.ratio * 10000) / 100,
  }))
  editorVisible.value = true
}

function addTier() {
  editorTiers.value.push({ minYuan: 0, maxYuan: null, ratioPercent: 5 })
}

function removeTier(i) {
  editorTiers.value.splice(i, 1)
}

function closeEditor() {
  editorVisible.value = false
}

async function submitEditor() {
  saving.value = true
  try {
    await performanceApi.saveRule(selected.value.orgId, editorType.value, {
      tiers: editorTiers.value.map((t) => ({
        minCent: Math.round(t.minYuan * 100),
        maxCent: t.maxYuan != null && t.maxYuan !== '' ? Math.round(t.maxYuan * 100) : null,
        ratio: t.ratioPercent / 100,
      })),
    })
    ElMessage.success('保存成功')
    editorVisible.value = false
    await loadRules(selected.value.orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function openHistory() {
  historyVisible.value = true
  try {
    const data = await performanceApi.history(selected.value.orgId)
    historyItems.value = data.items || []
  } catch {
    historyItems.value = []
  }
}

async function applyToDesc(ruleType) {
  try {
    await ElMessageBox.confirm(
      '确认将当前绩效提成方式应用到全部下级组织？（将覆盖下级组织已有的相同配置）',
      '应用到下级组织',
      { confirmButtonText: '应用', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const data = await performanceApi.applyToDescendants(selected.value.orgId, ruleType)
    ElMessage.success(`已应用到 ${data.applied} 个下级组织`)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '应用失败')
  }
}

function fmtCent(c) {
  return `¥${(c / 100).toFixed(2)}`
}
function operationLabel(op) {
  return { create: '配置', update: '修改', apply: '应用下级' }[op] || op
}
function fmtTiers(tiers) {
  if (!tiers) return ''
  return tiers.map((t) => `${fmtCent(t.minCent)}~${t.maxCent === null ? '∞' : fmtCent(t.maxCent)} ${(t.ratio * 100).toFixed(2)}%`).join('；')
}
function formatTime(t) {
  if (!t) return '-'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}

onMounted(loadAll)
</script>

<style scoped>
.pr-layout { display: flex; gap: 14px; align-items: flex-start; }
.tree-node-content { display: flex; align-items: center; gap: 8px; }
.node-level { color: var(--app-text-secondary); font-size: 12px; }

.org-header { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.org-title { font-size: 16px; font-weight: 600; color: #303133; }
.header-actions { margin-left: auto; }

.rule-card { margin-bottom: 14px; }
.rule-card__header { display: flex; align-items: center; gap: 10px; }
.rule-title { font-size: 14px; font-weight: 600; }
.rule-desc { color: #909399; font-size: 12px; margin-right: auto; }
.tiers-display { margin-top: 10px; }
.tier-row { font-size: 13px; color: #303133; padding: 2px 0; }

.tier-editor-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.tier-idx { width: 48px; color: #606266; font-size: 13px; }
.pct-suffix { color: #606266; font-size: 13px; }
.tier-actions { margin-top: 6px; }
.hint { color: #909399; font-size: 12px; margin-left: 10px; }
.muted { color: #909399; font-size: 12px; }
.history-diff { margin-top: 4px; word-break: break-all; }
</style>

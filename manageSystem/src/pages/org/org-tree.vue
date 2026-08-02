<template>
  <div class="org-page">
    <div class="page-header">
      <h2 class="page-title">组织人员管理</h2>
      <div class="header-actions">
        <el-button type="primary" @click="openCreate(null)">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>新建根组织
        </el-button>
        <el-button @click="loadTree">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </div>

    <div class="stats-bar" v-if="treeStats.totalNodes > 0">
      <el-tag type="info">组织总数：{{ treeStats.totalNodes }}</el-tag>
      <el-tag type="success">最大深度：{{ treeStats.maxDepth }}</el-tag>
    </div>

    <div class="tree-container" v-loading="loading">
      <el-empty v-if="!tree" description="暂无组织，请先创建根组织" />
      <el-tree
        v-else
        :data="treeData"
        :props="{ label: 'name', children: 'children' }"
        node-key="orgId"
        default-expand-all
        highlight-current
        @node-click="handleSelect"
      >
        <template #default="{ data }">
          <div class="tree-node-content">
            <span class="node-name">{{ data.name }}</span>
            <el-tag size="small" class="node-type-tag">{{ data.orgType }}</el-tag>
            <span class="node-level">L{{ data.level }}</span>
            <el-tag size="small" :type="data.status === 'disabled' ? 'danger' : 'success'">
              {{ data.status === 'disabled' ? '停用' : '正常' }}
            </el-tag>
          </div>
        </template>
      </el-tree>
    </div>

    <el-card v-if="selected" shadow="never" class="action-card">
      <template #header>
        <span>组织操作 — {{ selected.name }}</span>
      </template>
      <el-space wrap>
        <el-button size="small" type="primary" @click="openCreate(selected)">新增下级组织</el-button>
        <el-button size="small" type="warning" @click="openEdit(selected)">编辑</el-button>
        <el-button size="small" type="success" @click="openMigrate(selected)">迁移</el-button>
        <el-button size="small" type="danger" @click="handleDelete(selected)">删除</el-button>
        <el-button size="small" @click="showHistory(selected)">操作历史</el-button>
      </el-space>
    </el-card>

    <!-- Create/Edit dialog -->
    <el-dialog v-model="formVisible" :title="formMode === 'create' ? '新建组织' : '编辑组织'" width="460px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="上级组织" v-if="formMode === 'create'">
          <el-input :model-value="form.parentName || '（根组织）'" disabled />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="组织名称" maxlength="128" />
        </el-form-item>
        <el-form-item label="组织类型" required>
          <el-input v-model="form.orgType" placeholder="如 headquarters / region / branch" maxlength="50" />
        </el-form-item>
        <el-form-item label="排序" v-if="formMode === 'create'">
          <el-input-number v-model="form.sortOrder" :min="0" />
        </el-form-item>
        <el-form-item label="状态" v-if="formMode === 'edit'">
          <el-select v-model="form.status">
            <el-option label="正常" value="active" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- Migrate dialog -->
    <el-dialog v-model="migrateVisible" title="迁移组织" width="460px">
      <el-form label-width="90px">
        <el-form-item label="组织">
          <el-input :model-value="selected?.name" disabled />
        </el-form-item>
        <el-form-item label="目标上级">
          <el-select v-model="migrateTarget" filterable placeholder="选择新的上级组织（不选则为根）">
            <el-option v-for="o in flatOrgs" :key="o.orgId" :value="o.orgId" :label="`${o.name}（L${o.level}）`" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="migrateVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitMigrate">迁移</el-button>
      </template>
    </el-dialog>

    <!-- History dialog -->
    <el-dialog v-model="historyVisible" title="操作历史" width="520px">
      <el-timeline v-if="historyItems.length">
        <el-timeline-item v-for="(h, i) in historyItems" :key="i" :timestamp="h.createdAt || ''">
          {{ actionLabel(h.action) }}<span v-if="h.operatorId"> — 操作人 #{{ h.operatorId }}</span>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无操作记录" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { orgApi } from '@/api/org'

const loading = ref(false)
const saving = ref(false)
const tree = ref(null)
const selected = ref(null)
const flatOrgs = ref([])

const formVisible = ref(false)
const formMode = ref('create')
const form = reactive({ name: '', orgType: '', sortOrder: 0, status: 'active', parentId: null, parentName: '' })

const migrateVisible = ref(false)
const migrateTarget = ref(null)
const historyVisible = ref(false)
const historyItems = ref([])

const treeData = computed(() => (tree.value ? [tree.value] : []))
const treeStats = computed(() => ({
  totalNodes: tree.value ? countNodes(tree.value) : 0,
  maxDepth: tree.value ? maxDepth(tree.value) : 0,
}))

function countNodes(n) {
  return 1 + (n.children || []).reduce((s, c) => s + countNodes(c), 0)
}
function maxDepth(n) {
  return 1 + (n.children || []).reduce((s, c) => Math.max(s, maxDepth(c)), 0)
}
function flatten(n, acc = []) {
  acc.push(n)
  ;(n.children || []).forEach((c) => flatten(c, acc))
  return acc
}

async function loadTree() {
  loading.value = true
  try {
    const data = await orgApi.getTree()
    tree.value = data.tree || null
    flatOrgs.value = tree.value ? flatten(tree.value) : []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载组织树失败')
  } finally {
    loading.value = false
  }
}

function handleSelect(data) {
  selected.value = data
}

function openCreate(parent) {
  formMode.value = 'create'
  form.name = ''
  form.orgType = ''
  form.sortOrder = 0
  form.parentId = parent ? parent.orgId : null
  form.parentName = parent ? parent.name : ''
  formVisible.value = true
}

function openEdit(org) {
  formMode.value = 'edit'
  form.name = org.name
  form.orgType = org.orgType
  form.status = org.status
  form.sortOrder = org.sortOrder
  form.parentId = org.orgId
  formVisible.value = true
}

async function saveForm() {
  if (!form.name || !form.orgType) {
    ElMessage.warning('请填写名称与组织类型')
    return
  }
  saving.value = true
  try {
    if (formMode.value === 'create') {
      await orgApi.create({
        name: form.name,
        orgType: form.orgType,
        parentId: form.parentId || undefined,
        sortOrder: form.sortOrder,
      })
      ElMessage.success('创建成功')
    } else {
      await orgApi.update(selected.value.orgId, {
        name: form.name,
        orgType: form.orgType,
        status: form.status,
      })
      ElMessage.success('保存成功')
    }
    formVisible.value = false
    await loadTree()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function openMigrate(org) {
  migrateTarget.value = null
  migrateVisible.value = true
}

async function submitMigrate() {
  if (!selected.value) return
  saving.value = true
  try {
    await orgApi.migrate(selected.value.orgId, { newParentId: migrateTarget.value || undefined })
    ElMessage.success('迁移成功')
    migrateVisible.value = false
    await loadTree()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '迁移失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(org) {
  try {
    await ElMessageBox.confirm(`确认删除组织「${org.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await orgApi.remove(org.orgId)
    ElMessage.success('删除成功')
    selected.value = null
    await loadTree()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '删除失败')
  }
}

async function showHistory(org) {
  try {
    const data = await orgApi.history(org.orgId)
    historyItems.value = data.items || []
    historyVisible.value = true
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载历史失败')
  }
}

function actionLabel(a) {
  return { created: '创建', updated: '编辑', moved: '迁移', deleted: '删除' }[a] || a
}

onMounted(loadTree)
</script>

<style scoped>
.org-page { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.stats-bar { margin-bottom: 12px; display: flex; gap: 8px; }
.tree-node-content { display: flex; align-items: center; gap: 8px; }
.node-type-tag { margin-left: 4px; }
.action-card { margin-top: 16px; }
</style>

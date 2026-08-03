<template>
  <div class="org-page">
    <div class="page-header">
      <h2 class="page-title">组织人员管理</h2>
      <el-button @click="loadAll">
        <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <div class="org-layout">
      <!-- 左侧：组织结构树 -->
      <div class="tree-panel" v-loading="loading">
        <div class="panel-title">
          <span>组织结构</span>
        </div>
        <el-empty v-if="treeData.length === 0" description="暂无组织" :image-size="60" />
        <el-tree
          v-else
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
              <el-tag v-if="data.status === 'disabled'" size="small" type="danger" effect="plain">停用</el-tag>
            </div>
          </template>
        </el-tree>
      </div>

      <!-- 右侧：选中组织的详情 -->
      <div class="detail-panel">
        <el-empty v-if="!selected" description="请在左侧选择组织查看其下级组织与人员" :image-size="80" />

        <template v-else>
          <!-- 组织信息 -->
          <div class="org-header">
            <div class="org-header__top">
              <span class="org-title">{{ selected.name }}</span>
              <el-tag size="small" type="info" effect="plain">L{{ selected.level }}</el-tag>
              <el-tag size="small" :type="selected.status === 'disabled' ? 'danger' : 'success'" effect="plain">
                {{ selected.status === 'disabled' ? '停用' : '正常' }}
              </el-tag>
              <span v-if="selected.orgType" class="org-remark">{{ selected.orgType }}</span>
            </div>
            <el-space wrap class="org-actions">
              <el-button size="small" type="primary" @click="openCreate(selected)">新增下级组织</el-button>
              <el-button size="small" @click="openEdit(selected)">编辑</el-button>
              <el-button size="small" @click="showHistory(selected)">操作历史</el-button>
            </el-space>
          </div>

          <!-- 下级组织 -->
          <div class="section">
            <div class="section-title">下级组织（{{ subOrgs.length }}）</div>
            <el-table :data="subOrgs" border stripe size="small" style="width: 100%">
              <el-table-column prop="name" label="名称" min-width="140" />
              <el-table-column label="层级" width="70" align="center">
                <template #default="{ row }">L{{ row.level }}</template>
              </el-table-column>
              <el-table-column prop="orgType" label="备注" min-width="120">
                <template #default="{ row }">{{ row.orgType || '-' }}</template>
              </el-table-column>
              <el-table-column label="状态" width="70" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.status === 'disabled' ? 'danger' : 'success'" effect="plain">
                    {{ row.status === 'disabled' ? '停用' : '正常' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="资质状态" width="100" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.qualificationStatus === 'approved'" type="success" size="small">资质已审核</el-tag>
                  <el-tag v-else-if="row.qualificationStatus === 'reviewing'" type="warning" size="small">审核中</el-tag>
                  <el-tag v-else-if="row.qualificationStatus === 'rejected'" type="danger" size="small">未通过</el-tag>
                  <el-tag v-else type="info" size="small" effect="plain">无资质</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" link @click="openMigrate(row)">迁移</el-button>
                  <el-button size="small" link @click="goQualification(row)">资质管理</el-button>
                  <el-button size="small" link type="danger" @click="handleDelete(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 人员 -->
          <div class="section">
            <div class="section-title">
              <span>人员（{{ distributors.length }}）</span>
              <el-button size="small" type="primary" @click="openCreateDistributor">
                <el-icon style="margin-right: 4px"><Plus /></el-icon>新建分销员
              </el-button>
            </div>
            <el-table :data="distributors" v-loading="distLoading" border stripe size="small" style="width: 100%">
              <el-table-column prop="name" label="姓名" min-width="100" />
              <el-table-column prop="phone" label="手机号" width="130" />
              <el-table-column label="身份" width="110" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.orgRole === 'admin' ? 'warning' : 'info'">
                    {{ row.orgRole === 'admin' ? '组织管理员' : '成员' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.status === 'active' ? 'success' : 'danger'" effect="plain">
                    {{ row.status === 'active' ? '正常' : '停用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="280" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" link @click="openMoveOrg(row)">调整组织</el-button>
                  <el-button size="small" link :type="row.orgRole === 'admin' ? 'danger' : 'success'" @click="toggleRole(row)">
                    {{ row.orgRole === 'admin' ? '撤销管理员' : '设为管理员' }}
                  </el-button>
                  <el-button size="small" link @click="openReset(row)">重置密码</el-button>
                  <el-button size="small" link :type="row.status === 'active' ? 'warning' : 'success'" @click="toggleStatus(row)">
                    {{ row.status === 'active' ? '停用' : '启用' }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!distLoading && distributors.length === 0" description="该组织下暂无分销员" :image-size="60" />
          </div>
        </template>
      </div>
    </div>

    <!-- 新建/编辑组织 -->
    <el-dialog v-model="formVisible" :title="formMode === 'create' ? '新建组织' : '编辑组织'" width="460px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="上级组织" v-if="formMode === 'create'">
          <el-input :model-value="form.parentName || '（根组织）'" disabled />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="组织名称" maxlength="128" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.orgType" placeholder="备注（可选），如总部/区域/分站" maxlength="50" />
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

    <!-- 迁移组织 -->
    <el-dialog v-model="migrateVisible" title="迁移组织" width="460px">
      <el-form label-width="90px">
        <el-form-item label="组织">
          <el-input :model-value="migrateOrg?.name" disabled />
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

    <!-- 操作历史 -->
    <el-dialog v-model="historyVisible" title="操作历史" width="520px">
      <el-timeline v-if="historyItems.length">
        <el-timeline-item v-for="(h, i) in historyItems" :key="i" :timestamp="h.createdAt || ''">
          {{ actionLabel(h.action) }}<span v-if="h.operatorId"> — 操作人 #{{ h.operatorId }}</span>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无操作记录" />
    </el-dialog>

    <!-- 新建分销员 -->
    <el-dialog v-model="distCreateVisible" title="新建分销员" width="460px">
      <el-form :model="distForm" label-width="100px">
        <el-form-item label="所属组织">
          <el-input :model-value="selected?.name" disabled />
        </el-form-item>
        <el-form-item label="姓名" required><el-input v-model="distForm.name" maxlength="64" /></el-form-item>
        <el-form-item label="手机号" required><el-input v-model="distForm.phone" maxlength="11" /></el-form-item>
        <el-form-item label="初始密码" required><el-input v-model="distForm.initialPassword" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="distCreateVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreateDistributor">创建</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="420px">
      <el-input v-model="newPassword" type="password" show-password placeholder="新密码（至少8位）" />
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReset">重置</el-button>
      </template>
    </el-dialog>

    <!-- 调整组织归属 -->
    <el-dialog v-model="moveOrgVisible" title="调整组织归属" width="460px">
      <el-form label-width="90px">
        <el-form-item label="人员">
          <el-input :model-value="moveOrgRow?.name" disabled />
        </el-form-item>
        <el-form-item label="目标组织" required>
          <el-select v-model="moveOrgTarget" filterable placeholder="选择新的所属组织">
            <el-option v-for="o in flatOrgs" :key="o.orgId" :value="o.orgId" :label="`${o.name}（L${o.level}）`" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="moveOrgVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitMoveOrg">调整</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { orgApi, distributorApi } from '@/api/org'

const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const tree = ref(null)
const selected = ref(null)
const flatOrgs = ref([])

// 组织表单
const formVisible = ref(false)
const formMode = ref('create')
const form = reactive({ name: '', orgType: '', sortOrder: 0, status: 'active', parentId: null, parentName: '' })

// 迁移 / 历史
const migrateVisible = ref(false)
const migrateTarget = ref(null)
const migrateOrg = ref(null)
const historyVisible = ref(false)
const historyItems = ref([])

// 分销员
const distLoading = ref(false)
const distributors = ref([])
const distCreateVisible = ref(false)
const distForm = ref({ name: '', phone: '', initialPassword: '' })
const resetVisible = ref(false)
const newPassword = ref('')
const activeRow = ref(null)
const moveOrgVisible = ref(false)
const moveOrgTarget = ref(null)
const moveOrgRow = ref(null)

const treeData = computed(() => tree.value || [])
const subOrgs = computed(() => selected.value?.children || [])

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

async function loadAll() {
  loading.value = true
  try {
    const data = await orgApi.getTree()
    const roots = Array.isArray(data.tree) ? data.tree : (data.tree ? [data.tree] : [])
    tree.value = roots
    flatOrgs.value = roots.flatMap((r) => flatten(r))
    if (selected.value) {
      // 重载后尝试重新定位选中的组织（id 可能变化）
      const fresh = flatOrgs.value.find((o) => o.orgId === selected.value.orgId)
      handleSelect(fresh || null)
    } else if (roots.length > 0) {
      // 进入页面默认选中第一个根组织
      handleSelect(roots[0])
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载组织树失败')
  } finally {
    loading.value = false
  }
}

async function handleSelect(node) {
  selected.value = node
  if (node) await loadDistributors(node.orgId)
}

async function loadDistributors(orgId) {
  distLoading.value = true
  try {
    const data = await distributorApi.list(orgId, { limit: 100 })
    distributors.value = data.items || []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载人员失败')
    distributors.value = []
  } finally {
    distLoading.value = false
  }
}

function goQualification(org) {
  if (!org) return
  router.push({ path: '/org/detail', query: { orgId: org.orgId, orgName: org.name } })
}

// ── 组织 CRUD ──────────────────────────────────────────────
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
  if (!form.name) {
    ElMessage.warning('请填写组织名称')
    return
  }
  saving.value = true
  try {
    if (formMode.value === 'create') {
      await orgApi.create({
        name: form.name,
        orgType: form.orgType?.trim() || undefined,
        parentId: form.parentId || undefined,
        sortOrder: form.sortOrder,
      })
      ElMessage.success('创建成功')
    } else {
      await orgApi.update(selected.value.orgId, {
        name: form.name,
        orgType: form.orgType?.trim() || undefined,
        status: form.status,
      })
      ElMessage.success('保存成功')
    }
    formVisible.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function openMigrate(org) {
  migrateOrg.value = org
  migrateTarget.value = null
  migrateVisible.value = true
}

async function submitMigrate() {
  if (!migrateOrg.value) return
  saving.value = true
  try {
    await orgApi.migrate(migrateOrg.value.orgId, { newParentId: migrateTarget.value || undefined })
    ElMessage.success('迁移成功')
    migrateVisible.value = false
    await loadAll()
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
    await loadAll()
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

// ── 分销员操作 ─────────────────────────────────────────────
function openCreateDistributor() {
  distForm.value = { name: '', phone: '', initialPassword: '' }
  distCreateVisible.value = true
}

async function submitCreateDistributor() {
  const f = distForm.value
  if (!f.name || !/^\d{11}$/.test(f.phone) || f.initialPassword.length < 8) {
    ElMessage.warning('请填写完整信息（手机号11位、密码至少8位）')
    return
  }
  saving.value = true
  try {
    await distributorApi.create(selected.value.orgId, f)
    ElMessage.success('创建成功')
    distCreateVisible.value = false
    await loadDistributors(selected.value.orgId)
    await loadAll()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '创建失败')
  } finally {
    saving.value = false
  }
}

async function toggleRole(row) {
  const target = row.orgRole === 'admin' ? 'member' : 'admin'
  try {
    await ElMessageBox.confirm(target === 'admin' ? `确认将「${row.name}」设为组织管理员？` : `确认撤销「${row.name}」的组织管理员身份？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await distributorApi.setRole(row.distributorId, target)
    ElMessage.success('已更新')
    await loadDistributors(selected.value.orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '操作失败')
  }
}

async function toggleStatus(row) {
  try {
    await distributorApi.update(row.distributorId, { status: row.status === 'active' ? 'disabled' : 'active' })
    await loadDistributors(selected.value.orgId)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '操作失败')
  }
}

function openMoveOrg(row) {
  moveOrgRow.value = row
  moveOrgTarget.value = null
  moveOrgVisible.value = true
}

async function submitMoveOrg() {
  if (!moveOrgRow.value || !moveOrgTarget.value) {
    ElMessage.warning('请选择目标组织')
    return
  }
  saving.value = true
  try {
    await distributorApi.update(moveOrgRow.value.distributorId, { orgId: moveOrgTarget.value })
    ElMessage.success('已调整组织归属')
    moveOrgVisible.value = false
    await loadDistributors(selected.value.orgId)
    await loadAll()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '调整失败')
  } finally {
    saving.value = false
  }
}

function openReset(row) {
  activeRow.value = row
  newPassword.value = ''
  resetVisible.value = true
}

async function submitReset() {
  if (!activeRow.value || newPassword.value.length < 8) {
    ElMessage.warning('密码至少8位')
    return
  }
  try {
    await distributorApi.resetPassword(activeRow.value.distributorId, newPassword.value)
    ElMessage.success('已重置')
    resetVisible.value = false
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '重置失败')
  }
}

onMounted(loadAll)
</script>

<style scoped>
.org-page { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin: 0; }

.org-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.tree-panel {
  width: 300px;
  flex: none;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  min-height: 420px;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.tree-node-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.node-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-level { font-size: 12px; color: #909399; }

.detail-panel {
  flex: 1;
  min-width: 0;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 16px;
  min-height: 420px;
}

.org-header { padding-bottom: 14px; border-bottom: 1px solid #ebeef5; margin-bottom: 16px; }
.org-header__top { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.org-title { font-size: 18px; font-weight: 600; color: #303133; }
.org-remark { font-size: 13px; color: #909399; margin-left: 4px; }
.org-actions { margin-top: 4px; }

.section { margin-bottom: 20px; }
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}
</style>

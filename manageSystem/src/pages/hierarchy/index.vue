<template>
  <div class="hierarchy-page">
    <div class="page-header">
      <h2 class="page-title">层级管理</h2>
      <div class="header-actions">
        <el-button @click="refreshTree">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </div>

    <!-- Stats bar -->
    <div class="stats-bar" v-if="store.treeStats.totalNodes > 0">
      <el-tag type="info">总节点数：{{ store.treeStats.totalNodes }}</el-tag>
      <el-tag type="success">最大深度：{{ store.treeStats.maxDepth }}</el-tag>
    </div>

    <!-- Tree view -->
    <div class="tree-container" v-loading="store.loading">
      <el-empty v-if="!store.tree" description="暂无层级数据，请先创建根节点" />
      <el-tree
        v-else
        :data="treeData"
        :props="treeProps"
        node-key="nodeId"
        default-expand-all
        highlight-current
        :expand-on-click-node="true"
        @node-click="handleTreeNodeClick"
      >
        <template #default="{ node, data }">
          <div class="tree-node-content">
            <span class="node-name">{{ data.name }}</span>
            <el-tag size="small" :type="nodeTypeTagType(data.nodeType)" class="node-type-tag">
              {{ store.getNodeTypeLabel(data.nodeType) }}
            </el-tag>
            <span class="node-level">L{{ data.level }}</span>
            <span class="node-id">ID:{{ data.nodeId }}</span>
          </div>
        </template>
      </el-tree>
    </div>

    <!-- Hover action menu (shown on tree node context or right-click) -->
    <div class="tree-context-menu" v-if="selectedNode" style="margin-top: 16px">
      <el-card shadow="never">
        <template #header>
          <span>节点操作 — {{ selectedNode.name }}</span>
        </template>
        <div class="action-buttons">
          <el-button size="small" type="primary" plain @click="openAddChild">
            <el-icon style="margin-right: 4px"><Plus /></el-icon>添加子节点
          </el-button>
          <el-button size="small" type="warning" plain @click="openEdit">
            <el-icon style="margin-right: 4px"><Edit /></el-icon>编辑
          </el-button>
          <el-button size="small" type="success" plain @click="openMigrate">
            <el-icon style="margin-right: 4px"><Switch /></el-icon>迁移
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            @click="confirmDelete"
          >
            <el-icon style="margin-right: 4px"><Delete /></el-icon>删除
          </el-button>
        </div>
      </el-card>
    </div>

    <!-- Node form dialog (create/edit) -->
    <NodeForm
      v-model="showNodeForm"
      :is-edit="isEditing"
      :node-data="selectedNode"
      :parent-id="createParentId"
      @success="onNodeFormSuccess"
    />

    <!-- Migrate dialog -->
    <MigrateDialog
      v-model="showMigrate"
      :node-data="selectedNode"
      @success="onMigrateSuccess"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useHierarchyStore } from '@/stores/hierarchy'
import NodeForm from '@/components/hierarchy/NodeForm.vue'
import MigrateDialog from '@/components/hierarchy/MigrateDialog.vue'

const store = useHierarchyStore()

const treeData = computed(() => {
  if (!store.tree) return []
  return [store.tree]
})

const treeProps = {
  children: 'children',
  label: 'name',
}

const selectedNode = ref(null)
const showNodeForm = ref(false)
const isEditing = ref(false)
const createParentId = ref(null)
const showMigrate = ref(false)

const hasRoot = computed(() => store.tree !== null)

function nodeTypeTagType(type) {
  const types = {
    headquarters: '',
    region: 'success',
    branch: 'warning',
    promoter: 'info',
    terminal: 'danger',
  }
  return types[type] || 'info'
}

function handleTreeNodeClick(data) {
  selectedNode.value = data
}

// Cannot listen to click on el-tree directly in template; use a simple approach
// Select via the action buttons after the user visually picks a node
// For a real implementation, add @node-click handler

function openAddChild() {
  if (!selectedNode.value) return
  isEditing.value = false
  createParentId.value = selectedNode.value.nodeId
  showNodeForm.value = true
}

function openEdit() {
  if (!selectedNode.value) return
  isEditing.value = true
  showNodeForm.value = true
}

function openMigrate() {
  if (!selectedNode.value) return
  showMigrate.value = true
}

async function confirmDelete() {
  if (!selectedNode.value) return
  try {
    await ElMessageBox.confirm(
      `确定要删除节点 "${selectedNode.value.name}" 吗？只能删除没有子节点的叶子节点。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    await store.deleteNode(selectedNode.value.nodeId)
    selectedNode.value = null
  } catch {
    // user cancelled
  }
}

function onNodeFormSuccess() {
  selectedNode.value = null
}

function onMigrateSuccess() {
  selectedNode.value = null
}

async function refreshTree() {
  await store.fetchTree()
}

onMounted(() => {
  store.fetchTree()
})
</script>

<style scoped>
.hierarchy-page { padding: 10px 0; }
.page-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px;
}
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin: 0; }
.header-actions { display: flex; gap: 8px; }
.stats-bar { display: flex; gap: 12px; margin-bottom: 16px; }
.tree-container {
  background: #fff; border: 1px solid #ebeef5; border-radius: 4px;
  padding: 16px; min-height: 200px;
}

.tree-node-content {
  display: flex; align-items: center; gap: 8px; flex: 1;
  padding: 4px 0;
}
.node-name { font-weight: 500; font-size: 14px; color: #303133; }
.node-type-tag { flex-shrink: 0; }
.node-level { font-size: 12px; color: #909399; }
.node-id { font-size: 12px; color: #c0c4cc; margin-left: auto; }

.action-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
</style>

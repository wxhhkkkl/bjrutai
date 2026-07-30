import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const useHierarchyStore = defineStore('hierarchy', () => {
  // State
  const tree = ref(null)
  const treeStats = ref({ totalNodes: 0, maxDepth: 0 })
  const loading = ref(false)
  const currentSubtree = ref(null)

  // Node type labels
  const nodeTypeLabels = {
    headquarters: '总部',
    region: '大区',
    branch: '分部',
    promoter: '推广员',
    terminal: '终端',
  }

  const nodeTypeOptions = [
    { value: 'headquarters', label: '总部' },
    { value: 'region', label: '大区' },
    { value: 'branch', label: '分部' },
    { value: 'promoter', label: '推广员' },
    { value: 'terminal', label: '终端' },
  ]

  // Actions
  async function fetchTree() {
    loading.value = true
    try {
      const res = await http.get('/admin/hierarchy')
      const data = res.data
      tree.value = data.tree
      treeStats.value = { totalNodes: data.totalNodes, maxDepth: data.maxDepth }
    } catch (e) {
      ElMessage.error(e.userMessage || '获取层级树失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchSubtree(nodeId) {
    loading.value = true
    try {
      const res = await http.get(`/admin/hierarchy/nodes/${nodeId}`)
      currentSubtree.value = res.data
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '获取子树失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function createNode(data) {
    loading.value = true
    try {
      const res = await http.post('/admin/hierarchy/nodes', data)
      ElMessage.success('节点创建成功')
      await fetchTree()
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '创建节点失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateNode(nodeId, data) {
    loading.value = true
    try {
      const res = await http.put(`/admin/hierarchy/nodes/${nodeId}`, data)
      ElMessage.success('节点更新成功')
      await fetchTree()
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '更新节点失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deleteNode(nodeId) {
    loading.value = true
    try {
      await http.delete(`/admin/hierarchy/nodes/${nodeId}`)
      ElMessage.success('节点删除成功')
      await fetchTree()
    } catch (e) {
      ElMessage.error(e.userMessage || '删除节点失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function migrateBranch(nodeId, targetParentId) {
    loading.value = true
    try {
      const res = await http.post(`/admin/hierarchy/nodes/${nodeId}/migrate`, {
        targetParentId,
      })
      ElMessage.success('分支迁移成功')
      await fetchTree()
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '迁移失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  function getNodeTypeLabel(type) {
    return nodeTypeLabels[type] || type
  }

  return {
    // State
    tree,
    treeStats,
    loading,
    currentSubtree,
    // Config
    nodeTypeLabels,
    nodeTypeOptions,
    // Actions
    fetchTree,
    fetchSubtree,
    createNode,
    updateNode,
    deleteNode,
    migrateBranch,
    // Helpers
    getNodeTypeLabel,
  }
})

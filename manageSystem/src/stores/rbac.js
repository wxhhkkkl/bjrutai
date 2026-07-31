import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '@/api/http'

export const useRbacStore = defineStore('rbac', () => {
  // ── State ────────────────────────────────────────────────────
  const admins = ref([])
  const roles = ref([])
  const loading = ref(false)

  // ── Admin Account CRUD ───────────────────────────────────────
  async function fetchAdmins(params = {}) {
    loading.value = true
    try {
      const res = await http.get('/admin/accounts', { params })
      const body = res.data.data || res.data
      admins.value = body.items || []
      return body
    } finally {
      loading.value = false
    }
  }

  async function createAdmin(data) {
    const res = await http.post('/admin/accounts', data)
    await fetchAdmins()
    return res.data
  }

  async function updateAdmin(id, data) {
    const res = await http.put(`/admin/accounts/${id}`, data)
    await fetchAdmins()
    return res.data
  }

  async function disableAdmin(id) {
    const res = await http.post(`/admin/accounts/${id}/disable`)
    await fetchAdmins()
    return res.data
  }

  async function enableAdmin(id) {
    const res = await http.post(`/admin/accounts/${id}/enable`)
    await fetchAdmins()
    return res.data
  }

  // ── Role CRUD ────────────────────────────────────────────────
  async function fetchRoles() {
    loading.value = true
    try {
      const res = await http.get('/admin/roles')
      const body = res.data.data || res.data
      roles.value = body.items || []
      return body
    } finally {
      loading.value = false
    }
  }

  async function createRole(data) {
    const res = await http.post('/admin/roles', data)
    await fetchRoles()
    return res.data
  }

  async function updateRole(id, data) {
    const res = await http.put(`/admin/roles/${id}`, data)
    await fetchRoles()
    return res.data
  }

  async function deleteRole(id) {
    const res = await http.delete(`/admin/roles/${id}`)
    await fetchRoles()
    return res.data
  }

  return {
    admins,
    roles,
    loading,
    fetchAdmins,
    createAdmin,
    updateAdmin,
    disableAdmin,
    enableAdmin,
    fetchRoles,
    createRole,
    updateRole,
    deleteRole,
  }
})

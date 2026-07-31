import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '@/api/http'

const TOKEN_KEY = 'bjrutai_admin_token'
const REFRESH_TOKEN_KEY = 'bjrutai_admin_refresh_token'

export const useAuthStore = defineStore('auth', () => {
  // State
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const refreshToken = ref(localStorage.getItem(REFRESH_TOKEN_KEY) || '')
  const user = ref(null)
  const permissions = ref([])

  // Getters
  const isAuthenticated = computed(() => !!token.value)

  const userRole = computed(() => user.value?.role || null)

  function hasPermission(perm) {
    return permissions.value.includes(perm)
  }

  // Actions
  async function login(account, password) {
    const res = await http.post('/auth/admin-login', { account, password })
    const body = res.data.data || res.data
    // NOTE: destructure with different names to avoid shadowing the outer ref()
    const { accessToken: at, refreshToken: rt, user: userData } = body
    const perms = (userData && userData.permissions) || []
    token.value = at
    refreshToken.value = rt
    user.value = userData
    permissions.value = perms
    localStorage.setItem(TOKEN_KEY, at)
    localStorage.setItem(REFRESH_TOKEN_KEY, rt)
    return res.data
  }

  async function logout() {
    try {
      await http.post('/auth/logout')
    } catch {
      // Swallow — clear local state regardless
    }
    clearState()
  }

  async function refreshAccessToken() {
    if (!refreshToken.value) {
      throw new Error('No refresh token available')
    }
    const res = await http.post('/auth/refresh', {
      refreshToken: refreshToken.value,
    })
    const body = res.data.data || res.data
    const { accessToken: at, refreshToken: rt } = body
    token.value = at
    if (rt) {
      refreshToken.value = rt
      localStorage.setItem(REFRESH_TOKEN_KEY, rt)
    }
    localStorage.setItem(TOKEN_KEY, at)
    return res.data
  }

  async function fetchSession() {
    const res = await http.get('/auth/session')
    const body = res.data.data || res.data
    user.value = body.user
    permissions.value = body.permissions || []
  }

  function clearState() {
    token.value = ''
    refreshToken.value = ''
    user.value = null
    permissions.value = []
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }

  return {
    // State
    token,
    refreshToken,
    user,
    permissions,
    // Getters
    isAuthenticated,
    userRole,
    hasPermission,
    // Actions
    login,
    logout,
    refreshAccessToken,
    fetchSession,
  }
})

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
  async function login(username, password) {
    const res = await http.post('/auth/login', { username, password })
    const { access_token, refresh_token, user: userData, permissions: perms } = res.data
    token.value = access_token
    refreshToken.value = refresh_token
    user.value = userData
    permissions.value = perms || []
    localStorage.setItem(TOKEN_KEY, access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token)
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
      refresh_token: refreshToken.value,
    })
    const { access_token, refresh_token } = res.data
    token.value = access_token
    if (refresh_token) {
      refreshToken.value = refresh_token
      localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token)
    }
    localStorage.setItem(TOKEN_KEY, access_token)
    return res.data
  }

  async function fetchSession() {
    const res = await http.get('/auth/session')
    user.value = res.data.user
    permissions.value = res.data.permissions || []
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

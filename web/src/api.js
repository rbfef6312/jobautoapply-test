const API_BASE = '/api'
const REQUEST_TIMEOUT_MS = 60000

function getToken() {
  return localStorage.getItem('token')
}

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(getToken() && { Authorization: `Bearer ${getToken()}` }),
    },
  }
  if (body && method !== 'GET') {
    opts.body = JSON.stringify(body)
  }
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  opts.signal = controller.signal

  const res = await fetch(`${API_BASE}${path}`, opts).finally(() => clearTimeout(timeoutId))

  if (res.status === 401) {
    const returnPath = window.location.pathname !== '/login' ? window.location.pathname + window.location.search : ''
    if (returnPath) sessionStorage.setItem('login_return_path', returnPath)
    localStorage.removeItem('jobsdb_user')
    localStorage.removeItem('token')
    try {
      window.dispatchEvent(new CustomEvent('auth-logout', { detail: { message: '登录已失效，请重新登录' } }))
      window.dispatchEvent(new CustomEvent('app-toast', { detail: { message: '登录已失效，请重新登录', type: 'error', duration: 3000 } }))
    } catch {}
    setTimeout(() => {
      window.location.href = '/login'
    }, 100)
    throw new Error('登录已失效，请重新登录')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.detail || data.message || '请求失败')
  }
  return data
}

export function getLoginReturnPath() {
  const p = sessionStorage.getItem('login_return_path')
  if (p) {
    sessionStorage.removeItem('login_return_path')
    return p
  }
  return null
}

export const api = {
  auth: {
    register: (email, password, name) =>
      request('POST', '/auth/register', { email, password, name }),
    login: (email, password) => request('POST', '/auth/login', { email, password }),
    me: () => request('GET', '/auth/me'),
  },
  stats: () => request('GET', '/stats'),
  statsDaily: (days = 14) => request('GET', `/stats/daily?days=${days}`),
  monitor: {
    get: () => request('GET', '/monitor'),
    update: (data) => request('PUT', '/monitor', data),
  },
  jobsdb: {
    status: () => request('GET', '/jobsdb/status'),
    loginStart: (email) => request('POST', '/jobsdb/login/start', { email }),
    loginVerify: (code) => request('POST', '/jobsdb/login/verify', { code }),
    logout: () => request('DELETE', '/jobsdb/logout'),
  },
  classifications: () => request('GET', '/classifications'),
  apply: {
    run: (params) => request('POST', '/apply/run', params),
    status: () => request('GET', '/apply/status'),
    pause: () => request('POST', '/apply/pause'),
    resume: () => request('POST', '/apply/resume'),
    stop: () => request('POST', '/apply/stop'),
  },
  jobs: () => request('GET', '/jobs'),
  logs: (limit, ops = false) =>
    request('GET', `/logs?limit=${limit || 500}${ops ? '&ops=1' : ''}`),
  logReport: (action, detail = '') =>
    request('POST', '/logs/report', { action, detail }),
  excludedCompanies: {
    get: () => request('GET', '/excluded-companies'),
    update: (companies) => request('PUT', '/excluded-companies', { companies }),
  },
  external: {
    list: (includeDone = false) => request('GET', `/external${includeDone ? '?include_done=true' : ''}`),
    markDone: (url) => request('POST', '/external/mark-done', { url }),
    clear: () => request('DELETE', '/external'),
  },
}

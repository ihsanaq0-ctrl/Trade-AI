import { supabase } from './supabase'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const DEFAULT_TIMEOUT = 12000

const api = {
  async fetch(path, options = {}) {
    const { timeout = DEFAULT_TIMEOUT, headers = {}, method = 'GET', ...rest } = options
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeout)

    const fetchHeaders = { ...headers }

    // Automatically inject active Supabase JWT access token if not explicitly provided
    if (!fetchHeaders['Authorization'] && !fetchHeaders['authorization']) {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (session?.access_token) {
          fetchHeaders['Authorization'] = `Bearer ${session.access_token}`
        }
      } catch {
        // Continue unauthenticated if session retrieval fails
      }
    }

    // Only send Content-Type on requests with a body (POST, PUT, PATCH)
    if (rest.body) {
      fetchHeaders['Content-Type'] = 'application/json'
    }

    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method,
        ...rest,
        headers: fetchHeaders,
        signal: controller.signal,
      })
      clearTimeout(timer)

      if (!res.ok) {
        const body = await res.text().catch(() => '')
        let detailMsg = ''
        try {
          const parsed = JSON.parse(body)
          if (parsed && (parsed.detail || parsed.error || parsed.message)) {
            detailMsg = parsed.detail || parsed.error || parsed.message
          }
        } catch {}
        const err = new Error(detailMsg || `${res.status}: ${body || res.statusText}`)
        err.status = res.status
        err.detail = detailMsg
        throw err
      }

      return await res.json()
    } catch (err) {
      clearTimeout(timer)
      if (err.name === 'AbortError') {
        throw new Error('Request timed out - backend may be offline')
      }
      if (err.status) throw err
      if (err.message && (err.message.includes('Failed to fetch') || err.message.includes('NetworkError'))) {
        throw new Error('Cannot reach backend server (http://127.0.0.1:8002). Is it running?')
      }
      throw err
    }
  },

  get(path, opts) { return this.fetch(path, { ...opts, method: 'GET' }) },
  post(path, body, opts) { return this.fetch(path, { ...opts, method: 'POST', body: body ? JSON.stringify(body) : undefined }) },
  put(path, body, opts) { return this.fetch(path, { ...opts, method: 'PUT', body: body ? JSON.stringify(body) : undefined }) },
  del(path, opts) { return this.fetch(path, { ...opts, method: 'DELETE' }) },

  async checkHealth() {
    try {
      const data = await this.get('/api/health', { timeout: 5000 })
      return { ok: true, version: data.version }
    } catch {
      return { ok: false, error: 'Backend offline' }
    }
  },
}

export { API_BASE }
export default api

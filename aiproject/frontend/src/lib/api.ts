import {prepareSessionWorker} from './auth-session-worker'

export type Row = Record<string, any>
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}
let accessToken = ''
let tokenModeKnown = false
let sessionVersion = 0

export function getToken() {
  return !tokenModeKnown ? sessionStorage.getItem('ent-token') || accessToken : accessToken
}

export function setToken(token: string) {
  tokenModeKnown = true
  sessionVersion += 1
  accessToken = token
  sessionStorage.removeItem('ent-token')
}

function cookie(name: string) {
  return document.cookie.split('; ').find(item => item.startsWith(name + '='))?.slice(name.length + 1)
}

function csrf() {
  return cookie('__Host-edu_csrf') || cookie('edu_local_csrf')
}

let refreshPending: Promise<boolean> | undefined

export function refreshSession(): Promise<boolean> {
  if (refreshPending) return refreshPending
  if (!csrf()) return Promise.resolve(false)
  const version = sessionVersion
  const run = async () => {
    await prepareSessionWorker()
    if (version !== sessionVersion) return false
    const value = csrf()
    if (!value) return false
    const response = await fetch('/api/v1/auth/refresh', {
      method: 'POST', headers: {'X-CSRF-Token': value}, keepalive: true, signal: AbortSignal.timeout(30000),
    })
    if (!response.ok) return false
    const data = await response.json()
    if (version !== sessionVersion || typeof data.data?.access_token !== 'string') return false
    setToken(data.data.access_token)
    return true
  }
  const request = navigator.locks ? navigator.locks.request('yujiao-auth-refresh', run) : run()
  refreshPending = request.catch(() => false).finally(() => {refreshPending = undefined})
  return refreshPending
}
export function query(params: Row) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, String(v)) })
  return q.size ? '?' + q.toString() : ''
}
export async function api<T = any>(path: string, options: {method?: string; body?: unknown; timeout?: number; renewed?: boolean} = {}): Promise<T> {
  if ((options.method || 'GET') === 'POST' && (path === '/api/v1/auth/login' || path === '/api/v1/auth/logout')) {
    await prepareSessionWorker()
  }
  const token = getToken()
  let response: Response
  try {
    response = await fetch(path, {
      method: options.method || 'GET', headers: {...(options.body instanceof FormData ? {} : {'Content-Type': 'application/json'}), ...(token ? {Authorization: 'Bearer ' + token} : {}),
        ...(path.endsWith('/logout') && csrf() ? {'X-CSRF-Token': csrf()!} : {})},
      body: options.body === undefined || options.body instanceof FormData ? options.body : JSON.stringify(options.body), signal: AbortSignal.timeout(options.timeout || 30000),
    })
  } catch { throw new ApiError('连接失败或等待超时，请检查服务。写入操作请先查询核对后再重试。', 0) }
  const result = await response.json().catch(() => ({}))
  if (response.status === 401 && !path.endsWith('/login') && !path.endsWith('/logout') && !options.renewed) {
    if ((getToken() && getToken() !== token) || await refreshSession()) {
      return api<T>(path, {...options, renewed: true})
    }
  }
  if (!response.ok || (result.code !== undefined && result.code !== 0)) {
    const detail = result.detail || result.message || '操作未完成'
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: Row) => String(d.loc?.slice(1).join('.') || '') + '：' + d.msg).join('；') : JSON.stringify(detail)
    if (response.status === 401 && !path.endsWith('/login') && getToken() === token) window.dispatchEvent(new Event('ent-auth-expired'))
    throw new ApiError(message, response.status)
  }
  return result.data === undefined ? result : result.data
}


export async function download(path: string, filename: string, renewed = false): Promise<void> {
  const token = getToken()
  const response = await fetch(path, {
    headers: token ? {Authorization: 'Bearer ' + token} : {},
    signal: AbortSignal.timeout(30000),
  })
  if (response.status === 401 && !renewed && ((getToken() && getToken() !== token) || await refreshSession())) {
    return download(path, filename, true)
  }
  if (!response.ok) {
    if (response.status === 401 && getToken() === token) window.dispatchEvent(new Event('ent-auth-expired'))
    const result = await response.json().catch(() => ({}))
    throw new ApiError(typeof result.detail === 'string' ? result.detail : '附件下载失败', response.status)
  }
  const blob = await response.blob()
  if (!token || getToken() !== token) return
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 30000)
}

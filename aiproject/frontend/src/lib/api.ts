export type Row = Record<string, any>
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}
export function getToken() { return sessionStorage.getItem('ent-token') || '' }
export function setToken(token: string) { token ? sessionStorage.setItem('ent-token', token) : sessionStorage.removeItem('ent-token') }
export function query(params: Row) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, String(v)) })
  return q.size ? '?' + q.toString() : ''
}
export async function api<T = any>(path: string, options: {method?: string; body?: unknown; timeout?: number} = {}): Promise<T> {
  const token = getToken()
  let response: Response
  try {
    response = await fetch(path, {
      method: options.method || 'GET', headers: {'Content-Type': 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {})},
      body: options.body === undefined ? undefined : JSON.stringify(options.body), signal: AbortSignal.timeout(options.timeout || 30000),
    })
  } catch { throw new ApiError('连接失败或等待超时，请检查服务。写入操作请先查询核对后再重试。', 0) }
  const result = await response.json().catch(() => ({}))
  if (!response.ok || (result.code !== undefined && result.code !== 0)) {
    const detail = result.detail || result.message || '操作未完成'
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: Row) => String(d.loc?.slice(1).join('.') || '') + '：' + d.msg).join('；') : JSON.stringify(detail)
    if (response.status === 401 && !path.endsWith('/login')) window.dispatchEvent(new Event('ent-auth-expired'))
    throw new ApiError(message, response.status)
  }
  return result.data === undefined ? result : result.data
}

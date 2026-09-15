import type { ApiError, AppStatus, CaptureRun, Channel, ChromeState, PostDetail, PostSummary } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ApiError
    throw new Error(payload.detail || 'Không thể hoàn thành yêu cầu. Hãy thử lại.')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const archiveApi = {
  status: () => request<AppStatus>('/api/status'),
  openChrome: () => request<ChromeState>('/api/chrome/open', { method: 'POST' }),
  chromeStatus: () => request<ChromeState>('/api/chrome/status'),
  channels: () => request<Channel[]>('/api/channels'),
  addCurrentChannel: () => request<Channel>('/api/channels/current', { method: 'POST' }),
  removeChannel: (id: string) => request<void>(`/api/channels/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  completeSetup: () => request<{ setupComplete: boolean }>('/api/setup/complete', { method: 'POST' }),
  openStorage: () => request<void>('/api/storage/open', { method: 'POST' }),
  startCapture: (channelIds?: string[]) => request<{ id: string }>('/api/captures', {
    method: 'POST',
    body: JSON.stringify(channelIds?.length ? { channelIds } : {}),
  }),
  capture: () => request<CaptureRun | null>('/api/captures/current'),
  pauseCapture: (id: string) => request(`/api/captures/${id}/pause`, { method: 'POST' }),
  resumeCapture: (id: string) => request(`/api/captures/${id}/resume`, { method: 'POST' }),
  posts: (query = '', channelId = '') => {
    const params = new URLSearchParams()
    if (query) params.set('query', query)
    if (channelId) params.set('channelId', channelId)
    return request<{ items: PostSummary[]; nextCursor: string | null }>(`/api/posts?${params}`)
  },
  post: (id: string) => request<PostDetail>(`/api/posts/${encodeURIComponent(id)}`),
  openAttachment: (id: string) => request<void>(`/api/attachments/${encodeURIComponent(id)}/open`, { method: 'POST' }),
}

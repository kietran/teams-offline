import { afterEach, describe, expect, it, vi } from 'vitest'
import { archiveApi } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('capture API', () => {
  it('starts a new capture scoped to the failed channel when retrying', async () => {
    const fetchMock = vi.fn(async () => new Response('{"id":"new-run"}', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await archiveApi.startCapture(['ui-channel:abc'])

    expect(fetchMock).toHaveBeenCalledWith('/api/captures', expect.objectContaining({
      method: 'POST',
      body: '{"channelIds":["ui-channel:abc"]}',
    }))
  })
})

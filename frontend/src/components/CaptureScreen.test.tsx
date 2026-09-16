import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { CaptureScreen } from './CaptureScreen'

const noop = vi.fn()

it('separates downloaded, failed, and pending attachment counts', () => {
  render(<CaptureScreen
    channels={[]}
    chrome={{ installed: true, running: true, signed_in: true, needs_login: false, current_channel: null }}
    capture={{
      id: 'run-1', status: 'partial', current_channel_id: null,
      started_at: '2026-09-16T00:00:00Z', finished_at: '2026-09-16T00:01:00Z', summary: {},
      channels: [{
        channel_id: 'channel-1', displayName: 'Legal', teamName: 'Client', status: 'partial',
        posts_seen: 5, posts_completed: 5, expected_replies: 10, captured_replies: 10,
        files_captured: 8, files_failed: 2, files_pending: 3, error_message: null,
      }],
    }}
    busy={false}
    error={null}
    onManage={noop}
    onStart={noop}
    onPause={noop}
    onResume={noop}
    onRetry={noop}
  />)

  expect(screen.getByText(/8 tệp đã tải · 2 lỗi · 3 chưa thử/)).toBeInTheDocument()
})

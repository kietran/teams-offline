import { Info, Pause, Play, RefreshCw, Settings2 } from 'lucide-react'
import type { CaptureRun, Channel, ChromeState } from '../types'
import { StatusMark } from './StatusMark'

type Props = { channels: Channel[]; chrome: ChromeState; capture: CaptureRun | null; busy: boolean; error: string | null; onManage: () => void; onStart: () => void; onPause: () => void; onResume: () => void }

export function CaptureScreen({ channels, chrome, capture, busy, error, onManage, onStart, onPause, onResume }: Props) {
  const active = capture && ['queued', 'running', 'paused', 'interrupted'].includes(capture.status)
  const done = capture?.channels.reduce((sum, item) => sum + item.posts_completed, 0) || 0
  const seen = capture?.channels.reduce((sum, item) => sum + Math.max(item.posts_seen, item.posts_completed), 0) || 0
  const completedChannels = capture?.channels.filter(item => item.status === 'completed').length || 0
  const progress = capture?.channels.length ? Math.round((completedChannels / capture.channels.length) * 100) : 0
  const current = capture?.channels.find(item => item.channel_id === capture.current_channel_id)
  const hasHistory = channels.some(channel => channel.lastCapturedAt)
  return <main className="page" id="main-content" tabIndex={-1}>
    <div className="page-heading"><div><h1>Sao lưu từ Teams</h1><p>{active ? 'Ứng dụng đang lưu lần lượt từng kênh. Bạn vẫn có thể xem dữ liệu đã lưu.' : 'Lưu bài viết, bình luận, ảnh và tệp từ các kênh đã chọn.'}</p></div>
      {!active ? <button className="text-button" onClick={onManage}><Settings2 size={18} />Thay đổi kênh</button> : null}</div>
    {error ? <div className="notice error" role="alert">{error}</div> : null}
    {!chrome.signed_in ? <div className="notice warning">Chrome chưa đăng nhập Teams — mở Chrome và đăng nhập trước khi bắt đầu.</div> : null}
    {active ? <section className="progress-panel" aria-labelledby="progress-title"><div><span id="progress-title">Đang lưu kênh {Math.min(completedChannels + 1, capture.channels.length)}/{capture.channels.length}</span><h2>{current?.displayName || 'Đang chuẩn bị…'}</h2></div>
      {capture.status === 'running' || capture.status === 'queued' ? <button className="button secondary compact" onClick={onPause}><Pause size={18} />Tạm dừng</button> : <button className="button primary compact" onClick={onResume}><Play size={18} />Tiếp tục</button>}
      <div className="progress-track" role="progressbar" aria-label={`Đã lưu ${completedChannels} trong ${capture.channels.length} kênh`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{ width: `${progress}%` }} /></div>
      <p>{done}/{seen || '…'} bài viết · {capture.channels.reduce((sum, item) => sum + item.captured_replies, 0)} bình luận · {capture.channels.reduce((sum, item) => sum + item.files_captured, 0)} tệp</p></section> :
      <section className="start-panel"><div><h2>{hasHistory ? 'Sẵn sàng cập nhật' : 'Sẵn sàng sao lưu'}</h2><p>{channels.length} kênh đã chọn. Chrome sẽ lần lượt mở từng kênh và lưu dữ liệu về máy.</p></div><button className="button primary" disabled={busy || !chrome.signed_in || !channels.length} onClick={onStart}><RefreshCw size={19} />{hasHistory ? 'Cập nhật lại' : 'Bắt đầu lưu'}</button></section>}
    <section className="channel-status-list"><h2>Các kênh</h2>{(capture?.channels || channels.map(channel => ({ channel_id: channel.id, displayName: channel.displayName, teamName: channel.teamName, status: channel.lastCaptureStatus || 'queued', posts_seen: 0, posts_completed: 0, expected_replies: 0, captured_replies: 0, files_captured: 0, error_message: null }))).map(item =>
      <div className={`capture-row ${item.channel_id === capture?.current_channel_id ? 'selected' : ''}`} key={item.channel_id}><StatusMark status={item.status} /><span>{item.teamName}</span><strong>{item.displayName}</strong><small>{item.posts_completed ? `${item.posts_completed} bài viết · ${item.captured_replies} bình luận · ${item.files_captured} tệp` : item.error_message || '—'}</small>{['failed', 'partial'].includes(item.status) ? <button className="button secondary tiny" onClick={onResume}>Thử lại</button> : null}</div>)}</section>
    {active ? <div className="info-strip"><Info size={19} />Bạn có thể đóng ứng dụng. Lần sau quá trình sẽ tiếp tục từ đây.</div> : null}
  </main>
}

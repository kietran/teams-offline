import { Archive, CheckCircle2, Chrome, CloudDownload, FolderOpen } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { archiveApi } from './api'
import { ArchiveScreen } from './components/ArchiveScreen'
import { CaptureScreen } from './components/CaptureScreen'
import { SetupFlow } from './components/SetupFlow'
import type { AppStatus, Channel } from './types'

type View = 'capture' | 'archive'

export default function App() {
  const [status, setStatus] = useState<AppStatus | null>(null)
  const [channels, setChannels] = useState<Channel[]>([])
  const [view, setView] = useState<View>('capture')
  const [step, setStep] = useState(1)
  const [managing, setManaging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [nextStatus, nextChannels] = await Promise.all([archiveApi.status(), archiveApi.channels()])
      setStatus(nextStatus); setChannels(nextChannels)
      if (!nextStatus.setupComplete && nextStatus.chrome.signed_in && step === 1) setStep(2)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Không thể tải trạng thái ứng dụng.')
    }
  }, [step])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => { const timer = window.setInterval(() => void refresh(), 1000); return () => window.clearInterval(timer) }, [refresh])

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true); setError(null)
    try { await action(); await refresh() } catch (requestError) { setError(requestError instanceof Error ? requestError.message : 'Không thể hoàn thành yêu cầu.') } finally { setBusy(false) }
  }

  if (!status) return <main className="loading-screen"><div className="spinner" /><p>Đang mở kho lưu trữ…</p></main>

  const inSetup = !status.setupComplete || managing
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Bỏ qua đến nội dung chính</a>
    <header className="topbar"><div className="brand"><span><Archive size={22} /></span><strong>Teams Offline Archive</strong></div>
      {!inSetup ? <nav aria-label="Điều hướng chính"><button className={view === 'capture' ? 'active' : ''} onClick={() => setView('capture')}><CloudDownload size={20} />Sao lưu</button><button className={view === 'archive' ? 'active' : ''} onClick={() => setView('archive')}><FolderOpen size={20} />Kho lưu trữ</button></nav> : null}
      <div className={`chrome-pill ${status.chrome.signed_in || (!inSetup && view === 'archive') ? 'connected' : ''}`}>{!inSetup && view === 'archive' ? <><CheckCircle2 size={18} />Đã lưu {channels.length} kênh</> : <>{status.chrome.signed_in ? <CheckCircle2 size={18} /> : <Chrome size={18} />}{status.chrome.signed_in ? 'Chrome đã kết nối' : 'Chrome chưa kết nối'}</>}</div>
    </header>
    {inSetup ? <SetupFlow status={status} channels={channels} step={step} busy={busy} error={error} onStep={setStep}
      onOpenChrome={() => void run(archiveApi.openChrome)} onAddChannel={() => void run(archiveApi.addCurrentChannel)}
      onRemoveChannel={id => void run(() => archiveApi.removeChannel(id))} onOpenStorage={() => void run(archiveApi.openStorage)}
      onComplete={() => void run(async () => { await archiveApi.completeSetup(); setManaging(false) })} /> :
      view === 'capture' ? <CaptureScreen channels={channels} chrome={status.chrome} capture={status.capture} busy={busy} error={error}
        onManage={() => { setStep(2); setManaging(true) }} onStart={() => void run(archiveApi.startCapture)}
        onPause={() => status.capture && void run(() => archiveApi.pauseCapture(status.capture!.id))}
        onResume={() => status.capture && void run(() => archiveApi.resumeCapture(status.capture!.id))}
        onRetry={channelId => void run(() => archiveApi.startCapture([channelId]))} /> : <ArchiveScreen channels={channels} />}
  </div>
}

import { Check, Chrome, FolderOpen, Plus, Trash2 } from 'lucide-react'
import type { AppStatus, Channel } from '../types'

type Props = {
  status: AppStatus
  channels: Channel[]
  step: number
  busy: boolean
  error: string | null
  onStep: (step: number) => void
  onOpenChrome: () => void
  onAddChannel: () => void
  onRemoveChannel: (id: string) => void
  onOpenStorage: () => void
  onComplete: () => void
}

const steps = ['Kết nối Chrome', 'Chọn kênh', 'Nơi lưu']

export function SetupFlow(props: Props) {
  const { status, channels, step, busy, error } = props
  return <div className="setup-layout">
    <aside className="setup-rail" aria-label="Tiến độ thiết lập">
      <ol>{steps.map((label, index) => {
        const number = index + 1
        const complete = number < step || (number === 1 && status.chrome.signed_in)
        return <li key={label} className={number === step ? 'active' : complete ? 'complete' : ''}>
          <span>{complete ? <Check size={18} /> : number}</span><div><strong>{number}. {label}</strong><small>{complete ? 'Đã hoàn thành' : number === step ? 'Đang thực hiện' : 'Chưa thực hiện'}</small></div>
        </li>
      })}</ol>
    </aside>
    <main className="setup-main" id="main-content" tabIndex={-1}>
      {step === 1 ? <section className="setup-content">
        <p className="step-count">Bước 1 / 3</p><h1>Mở Teams trong Chrome</h1>
        <p className="lead">Bạn đăng nhập trực tiếp trong Chrome. Ứng dụng không nhìn thấy hoặc lưu mật khẩu.</p>
        <div className="instruction-single"><Chrome size={30} /><div><h2>Google Chrome</h2><p>Chrome sẽ mở bằng một hồ sơ riêng dành cho kho lưu trữ này.</p></div></div>
        {status.chrome.signed_in ? <div className="notice success"><Check size={19} /> Chrome đã kết nối</div> : null}
        {error ? <div className="notice error" role="alert">{error}</div> : null}
        <div className="setup-actions"><button className="button primary" disabled={busy} onClick={status.chrome.signed_in ? () => props.onStep(2) : props.onOpenChrome}>{status.chrome.signed_in ? 'Tiếp tục' : busy ? 'Đang mở Chrome…' : 'Mở Chrome'}</button></div>
      </section> : null}
      {step === 2 ? <section className="setup-content wide">
        <p className="step-count">Bước 2 / 3</p><h1>Chọn kênh cần lưu</h1>
        <p className="lead">Thêm khoảng 5–10 kênh bạn muốn lưu để xem lại khi cần.</p>
        <div className="instruction-grid">
          <div><b>1</b><strong>Mở Teams trong Chrome</strong><span>Dùng cửa sổ Chrome ứng dụng đã mở.</span></div>
          <div><b>2</b><strong>Mở kênh cần lưu</strong><span>Chọn kênh từ danh sách Teams.</span></div>
          <div><b>3</b><strong>Bấm Thêm kênh đang mở</strong><span>Quay lại ứng dụng để thêm.</span></div>
        </div>
        <button className="button primary add-channel" disabled={busy} onClick={props.onAddChannel}><Plus size={19} />{busy ? 'Đang đọc kênh…' : 'Thêm kênh đang mở'}</button>
        {error ? <div className="notice error" role="alert">{error}</div> : null}
        <div className="channel-list"><h2>Kênh đã chọn ({channels.length})</h2>
          {channels.length ? channels.map(channel => <div className="channel-row" key={channel.id}><div><span>{channel.teamName}</span><strong>{channel.displayName}</strong></div><span className="ready"><Check size={17} /> Sẵn sàng</span><button className="text-button danger" onClick={() => props.onRemoveChannel(channel.id)}><Trash2 size={17} />Xóa</button></div>) : <p className="empty-line">Chưa có kênh nào được thêm.</p>}
        </div>
        <div className="setup-actions"><button className="button secondary" onClick={() => props.onStep(1)}>Quay lại</button><button className="button primary" disabled={!channels.length} onClick={() => props.onStep(3)}>Tiếp tục</button></div>
      </section> : null}
      {step === 3 ? <section className="setup-content">
        <p className="step-count">Bước 3 / 3</p><h1>Nơi lưu dữ liệu</h1>
        <p className="lead">Bài viết, bình luận, ảnh và tệp sẽ được lưu trên máy này.</p>
        <div className="storage-panel"><FolderOpen size={28} /><div><h2>Thư mục lưu trữ</h2><p>{status.storage.path}</p></div><button className="button secondary compact" onClick={props.onOpenStorage}>Mở thư mục</button></div>
        {error ? <div className="notice error" role="alert">{error}</div> : null}
        <div className="setup-actions"><button className="button secondary" onClick={() => props.onStep(2)}>Quay lại</button><button className="button primary" disabled={busy} onClick={props.onComplete}>Hoàn tất thiết lập</button></div>
      </section> : null}
    </main>
  </div>
}

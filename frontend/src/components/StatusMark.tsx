import { CheckCircle2, CircleAlert, Clock3, LoaderCircle } from 'lucide-react'

const labels: Record<string, string> = {
  completed: 'Đã lưu', partial: 'Cần thử lại', failed: 'Cần thử lại',
  running: 'Đang lưu', queued: 'Đang chờ', paused: 'Đã tạm dừng', interrupted: 'Có thể tiếp tục',
}

export function StatusMark({ status }: { status: string }) {
  const Icon = status === 'completed' ? CheckCircle2 : status === 'running' ? LoaderCircle :
    status === 'partial' || status === 'failed' ? CircleAlert : Clock3
  return <span className={`status status--${status}`}><Icon size={19} aria-hidden="true" />{labels[status] || status}</span>
}

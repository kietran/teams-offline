export type ChromeState = {
  installed: boolean
  running: boolean
  signed_in: boolean
  needs_login: boolean
  current_channel: { displayName: string; pageTitle: string } | null
}

export type Channel = {
  id: string
  teamId: string
  teamName: string
  displayName: string
  membershipType: string
  identityConfidence: string
  lastCaptureStatus: string | null
  lastCapturedAt: string | null
}

export type CaptureChannel = {
  channel_id: string
  displayName: string
  teamName: string
  status: string
  posts_seen: number
  posts_completed: number
  expected_replies: number
  captured_replies: number
  files_captured: number
  error_message: string | null
}

export type CaptureRun = {
  id: string
  status: string
  current_channel_id: string | null
  started_at: string
  finished_at: string | null
  summary: Record<string, number>
  channels: CaptureChannel[]
}

export type AppStatus = {
  setupComplete: boolean
  chrome: ChromeState
  storage: { mode: 'local'; path: string }
  selectedChannelCount: number
  capture: CaptureRun | null
}

export type PostSummary = {
  id: string
  subject: string | null
  bodyText: string
  authorName: string
  createdAt: string | null
  channelName: string
  teamName: string
  replyCount: number
  attachmentCount: number
}

export type StoredMessage = {
  id: string
  author_name: string
  subject: string | null
  body_html: string
  body_text: string
  created_at: string | null
  channelName: string
  teamName: string
}

export type StoredAttachment = {
  id: string
  name: string
  size_bytes: number | null
  status: string
}

export type PostDetail = {
  root: StoredMessage
  replies: StoredMessage[]
  attachments: StoredAttachment[]
}

export type ApiError = { detail?: string }

import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const status = { setupComplete:false, chrome:{installed:true,running:false,signed_in:false,needs_login:false,current_channel:null}, storage:{mode:'local',path:'/tmp/archive'}, selectedChannelCount:0, capture:null }

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url=String(input)
    if(url.includes('/api/channels')) return new Response('[]',{status:200,headers:{'Content-Type':'application/json'}})
    return new Response(JSON.stringify(status),{status:200,headers:{'Content-Type':'application/json'}})
  }))
})

describe('Chrome capture setup', () => {
  it('shows the three-step low-tech setup flow', async () => {
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading',{name:'Mở Teams trong Chrome'})).toBeInTheDocument())
    expect(screen.getByText('1. Kết nối Chrome')).toBeInTheDocument()
    expect(screen.getByText('2. Chọn kênh')).toBeInTheDocument()
    expect(screen.getByText('3. Nơi lưu')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Mở Chrome'})).toBeEnabled()
  })
})

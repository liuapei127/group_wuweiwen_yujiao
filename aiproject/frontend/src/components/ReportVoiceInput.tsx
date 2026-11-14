import {useEffect, useRef, useState} from 'react'
import {Alert, Button, Input, Space, Typography} from 'antd'
import {api} from '../lib/api'
import workletUrl from './report-audio-worklet.js?url'

const maxSeconds = 120
const targetRate = 16_000

type Capture = {
  context: AudioContext
  stream: MediaStream
  source: MediaStreamAudioSourceNode
  worklet: AudioWorkletNode
  chunks: Float32Array[]
  sampleCount: number
  limit: ReturnType<typeof setTimeout>
}

function release(capture: Capture) {
  clearTimeout(capture.limit)
  capture.worklet.port.onmessage = null
  capture.worklet.port.close()
  capture.worklet.disconnect()
  capture.source.disconnect()
  capture.stream.getTracks().forEach(track => track.stop())
  void capture.context.close().catch(() => undefined)
}

async function encodeWav(capture: Capture) {
  const {sampleRate} = capture.context
  const samples = new AudioBuffer({length: capture.sampleCount, sampleRate})
  const channel = samples.getChannelData(0)
  let offset = 0
  for (const chunk of capture.chunks) {
    channel.set(chunk, offset)
    offset += chunk.length
  }
  const frameCount = Math.max(1, Math.floor(channel.length * targetRate / sampleRate))
  const context = new OfflineAudioContext(1, frameCount, targetRate)
  const source = context.createBufferSource()
  source.buffer = samples
  source.connect(context.destination)
  source.start()
  const frames = (await context.startRendering()).getChannelData(0)
  const wav = new DataView(new ArrayBuffer(44 + frames.length * 2))
  for (const [offset, name] of [[0, 'RIFF'], [8, 'WAVE'], [12, 'fmt '], [36, 'data']] as const) {
    for (let i = 0; i < name.length; i++) wav.setUint8(offset + i, name.charCodeAt(i))
  }
  wav.setUint32(4, wav.byteLength - 8, true)
  wav.setUint32(16, 16, true)
  wav.setUint16(20, 1, true)
  wav.setUint16(22, 1, true)
  wav.setUint32(24, targetRate, true)
  wav.setUint32(28, targetRate * 2, true)
  wav.setUint16(32, 2, true)
  wav.setUint16(34, 16, true)
  wav.setUint32(40, frames.length * 2, true)
  frames.forEach((sample, index) => {
    const capped = Math.max(-1, Math.min(1, sample))
    wav.setInt16(44 + index * 2, capped * (capped < 0 ? 32768 : 32767), true)
  })
  return new Blob([wav.buffer], {type: 'audio/wav'})
}

export function ReportVoiceInput({onInsert}: {onInsert: (text: string) => boolean}) {
  const active = useRef<Capture | null>(null)
  const alive = useRef(false)
  const [phase, setPhase] = useState<'idle' | 'preparing' | 'recording' | 'transcribing'>('idle')
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      if (active.current) release(active.current)
      active.current = null
    }
  }, [])

  async function stopAndTranscribe() {
    const capture = active.current
    if (!capture) return
    active.current = null
    release(capture)
    setPhase('transcribing')
    setError('')
    try {
      if (!capture.sampleCount) throw new Error('录音太短，请重新录制')
      const audio = await encodeWav(capture)
      if (!alive.current) return
      const payload = new FormData()
      payload.append('file', audio, 'daily-report.wav')
      const result = await api<{text: string}>('/api/v1/employee-reports/transcribe', {
        method: 'POST', body: payload, timeout: 130_000,
      })
      if (alive.current) setDraft(result.text)
    } catch (cause) {
      if (alive.current) setError(cause instanceof Error ? cause.message : '录音转写失败')
    } finally {
      if (alive.current) setPhase('idle')
    }
  }

  async function start() {
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
      setError('当前环境无法录音，请在 HTTPS 或本机地址使用支持麦克风的浏览器')
      return
    }
    setPhase('preparing')
    setError('')
    let stream: MediaStream | undefined
    let context: AudioContext | undefined
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1}})
      if (!alive.current) {
        stream.getTracks().forEach(track => track.stop())
        return
      }
      context = new AudioContext()
      await context.resume()
      await context.audioWorklet.addModule(workletUrl)
      if (!alive.current) {
        stream.getTracks().forEach(track => track.stop())
        await context.close()
        return
      }
      const source = context.createMediaStreamSource(stream)
      const worklet = new AudioWorkletNode(context, 'report-audio-capture', {channelCount: 1, channelCountMode: 'explicit'})
      const capture: Capture = {
        context, stream, source, worklet, chunks: [], sampleCount: 0,
        limit: setTimeout(() => void stopAndTranscribe(), maxSeconds * 1000),
      }
      active.current = capture
      worklet.port.onmessage = ({data}: MessageEvent<Float32Array>) => {
        if (active.current !== capture) return
        const available = Math.floor(capture.context.sampleRate * maxSeconds) - capture.sampleCount
        const chunk = data.length > available ? data.slice(0, available) : data
        capture.chunks.push(chunk)
        capture.sampleCount += chunk.length
        if (chunk.length >= available) void stopAndTranscribe()
      }
      source.connect(worklet)
      worklet.connect(context.destination)
      setPhase('recording')
    } catch {
      if (active.current) {
        release(active.current)
        active.current = null
      } else {
        stream?.getTracks().forEach(track => track.stop())
        if (context) void context.close().catch(() => undefined)
      }
      if (alive.current) {
        setError('无法使用麦克风，请检查浏览器权限和录音设备')
        setPhase('idle')
      }
    }
  }

  return <Space orientation="vertical" style={{width: '100%', marginBottom: 16}}>
    <Typography.Text strong>录音转写</Typography.Text>
    <Typography.Text type="secondary">每段最多 2 分钟。结束录音后会发送音频进行转写，请核对文字后再插入日报。</Typography.Text>
    <Space wrap>
      {phase === 'recording' ? <>
        <Button type="primary" onClick={() => void stopAndTranscribe()}>结束录音并转写</Button>
        <Button onClick={() => {
          if (active.current) release(active.current)
          active.current = null
          setPhase('idle')
        }}>取消录音</Button>
      </> : <Button disabled={phase === 'transcribing'} loading={phase === 'preparing'} onClick={() => void start()}>开始录音</Button>}
      {phase === 'recording' && <Typography.Text type="danger" role="status">录音中</Typography.Text>}
      {phase === 'transcribing' && <Typography.Text role="status">正在转写…</Typography.Text>}
    </Space>
    {error && <Alert showIcon type="error" title={error}/>}
    {draft && <>
      <Input.TextArea aria-label="转写草稿" value={draft} maxLength={10000} rows={4} onChange={event => setDraft(event.target.value)}/>
      <Space>
        <Button disabled={phase !== 'idle' || !draft.trim()} onClick={() => {
          if (onInsert(draft.trim())) {setDraft(''); setError('')}
          else setError('转写内容超过日报正文长度，请缩短后再插入')
        }}>插入日报正文</Button>
        <Button onClick={() => setDraft('')}>清除草稿</Button>
      </Space>
    </>}
  </Space>
}

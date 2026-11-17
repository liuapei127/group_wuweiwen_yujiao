export async function readChatStream<T>(response: Response, onText: (text: string) => void, makeError: (message: string, status: number) => Error): Promise<T> {
  if (!response.body) throw makeError('回复流不可用，请先查看记录后再试。', 0)
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  try {
    for (;;) {
      const {value, done} = await reader.read()
      if (done) break
      buffer += value
      let end: number
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        const event = frame.match(/^event: (.+)$/m)?.[1]
        const payload = frame.match(/^data: (.+)$/m)?.[1]
        if (!payload) continue
        const data = JSON.parse(payload)
        if (event === 'text' && typeof data.text === 'string') onText(data.text)
        if (event === 'result') return data.data as T
        if (event === 'error') throw makeError(String(data.message || '回复中断'), Number(data.status) || 0)
      }
    }
    throw makeError('回复连接中断，请先查看记录后再试。', 0)
  } finally {
    void reader.cancel().catch(() => undefined)
  }
}

type Task = {id: string; version: number; status: string; ordinal?: number; updated_at?: string}
const ended = new Set(['submitted', 'cancelled', 'expired'])

// A delayed history read must not replace a newer confirmation or attachment.
export function newestAssistantTask<T extends Task>(server: T | undefined, local: T | undefined, localTime = 0, serverTime = 0): T | undefined {
  if (!server) return local
  if (!local) return server
  if (server.id !== local.id) {
    if (server.ordinal !== undefined && local.ordinal !== undefined && server.ordinal !== local.ordinal) return local.ordinal > server.ordinal ? local : server
    if (server.updated_at && local.updated_at && server.updated_at !== local.updated_at) return local.updated_at > server.updated_at ? local : server
    return localTime > serverTime ? local : server
  }
  if (local.version !== server.version) return local.version > server.version ? local : server
  return ended.has(local.status) && !ended.has(server.status) ? local : server
}

type Message = {id: number; role: string; content: string}

// A previous identical answer is not proof that the current user/assistant pair was saved.
export function assistantTurnStored(messages: Message[], query: string, answer: string, afterMessageId: number): boolean {
  for (let i = 0; i < messages.length - 1; i += 1) {
    const user = messages[i], assistant = messages[i + 1]
    if (user.id > afterMessageId && user.role === 'user' && user.content === query && assistant.role === 'assistant' && assistant.content === answer) return true
  }
  return false
}

export function hasRecordedReply(messages: {id: number; role: string; content: string}[], reply?: {answer: string; clientQuery?: string; afterMessageId?: number}): boolean {
  return !!reply?.clientQuery && assistantTurnStored(messages, reply.clientQuery, reply.answer, reply.afterMessageId || 0)
}

// Keep locally received answers in their original place when several history writes fail.
export function orderAssistantTurns<T extends {id: number}, L extends {id: number; afterMessageId: number}>(messages: T[], localTurns: L[]): ({server: T; local?: never} | {local: L; server?: never})[] {
  const entries: ({server: T; local?: never} | {local: L; server?: never})[] = [...messages.map(server => ({server})), ...localTurns.map(local => ({local}))]
  return entries.sort((a, b) => {
    if (a.server && b.server) return a.server.id - b.server.id
    if (a.local && b.local) return a.local.afterMessageId - b.local.afterMessageId || a.local.id - b.local.id
    if (a.local && b.server) return a.local.afterMessageId < b.server.id ? -1 : 1
    if (a.server && b.local) return a.server.id <= b.local.afterMessageId ? -1 : 1
    return 0
  })
}


type CardPresentation = {facts_kind?: string; intent?: string; knowledge_keys?: string[]}
export function assistantCardLayout(presentation: CardPresentation | undefined, card: {source_url?: string}): 'source' | 'fact' {
  if (presentation?.facts_kind === 'student_record') return 'fact'
  if (presentation?.facts_kind === 'public_knowledge') return 'source'
  return card.source_url?.toLowerCase().startsWith('https://') && (presentation?.intent === 'ask' || !!presentation?.knowledge_keys?.length) ? 'source' : 'fact'
}

type ReadingPosition = {scrollHeight: number; viewportHeight: number; responseTop?: number}
// The start remains stable as text or sources grow; scrolling to scrollHeight hides the answer.
export function replyScrollTarget(position: ReadingPosition & {followReply: boolean}): number | undefined {
  if (!position.followReply) return undefined
  return Math.max(0, Math.min((position.responseTop || 0) - 8, position.scrollHeight - position.viewportHeight))
}

export function replyReadingAction(position: ReadingPosition & {scrollTop: number}): 'latest' | 'continue' | undefined {
  if (position.responseTop === undefined || position.scrollHeight - position.viewportHeight - position.scrollTop < 20) return undefined
  return position.responseTop !== undefined && position.scrollTop < position.responseTop - 24 ? 'latest' : 'continue'
}


export function additionalOfficialSources(card: {source_url?: string; sources?: {title: string; url: string}[]}): {title: string; url: string}[] {
  const seen = new Set([card.source_url])
  return (card.sources || []).filter(source => {
    if (!source.url.toLowerCase().startsWith('https://') || seen.has(source.url)) return false
    seen.add(source.url)
    return true
  })
}

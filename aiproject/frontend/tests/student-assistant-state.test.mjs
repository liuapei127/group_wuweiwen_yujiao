import test from 'node:test'
import assert from 'node:assert/strict'
import {newestAssistantTask, hasRecordedReply, assistantTurnStored, orderAssistantTurns, assistantCardLayout, replyScrollTarget, replyReadingAction, additionalOfficialSources} from '../src/pages/student-assistant-state.ts'

test('a successful confirmation remains submitted while an old history read arrives', () => {
  const history = {id: 'leave-1', version: 4, status: 'awaiting_confirmation'}
  const receipt = {id: 'leave-1', version: 5, status: 'submitted', result: {id: 19}}
  assert.equal(newestAssistantTask(history, receipt, 10, 20), receipt)
})

test('a saved attachment invalidates the old confirmation even if refresh fails', () => {
  const history = {id: 'leave-1', version: 2, status: 'awaiting_confirmation'}
  const updated = {id: 'leave-1', version: 3, status: 'awaiting_confirmation', attachment: {filename: 'proof.pdf'}}
  assert.equal(newestAssistantTask(history, updated, 10, 20), updated)
})

test('a higher server version from another tab wins over a local receipt', () => {
  const local = {id: 'leave-1', version: 3, status: 'awaiting_confirmation'}
  const server = {id: 'leave-1', version: 4, status: 'cancelled'}
  assert.equal(newestAssistantTask(server, local, 50, 10), server)
})

test('different tasks follow the newest response rather than retaining an old receipt', () => {
  const old = {id: 'leave-1', version: 9, status: 'submitted'}
  const fresh = {id: 'feedback-2', version: 1, status: 'collecting'}
  assert.equal(newestAssistantTask(old, fresh, 20, 10), fresh)
  assert.equal(newestAssistantTask(fresh, old, 10, 20), fresh)
})

test('an ended status is retained at an equal version', () => {
  const active = {id: 'leave-1', version: 3, status: 'awaiting_confirmation'}
  const cancelled = {id: 'leave-1', version: 3, status: 'cancelled'}
  const expired = {id: 'leave-1', version: 3, status: 'expired'}
  assert.equal(newestAssistantTask(active, cancelled), cancelled)
  assert.equal(newestAssistantTask(expired, active), expired)
})

test('initial or temporarily unavailable history does not hide a local task', () => {
  const task = {id: 'leave-1', version: 1, status: 'collecting'}
  assert.equal(newestAssistantTask(undefined, task), task)
  assert.equal(newestAssistantTask(task, undefined), task)
  assert.equal(newestAssistantTask(undefined, undefined), undefined)
})

test('a later fetch cannot make an older task win over a higher ordinal', () => {
 const fresh={id:'task2',version:1,status:'collecting',ordinal:2}
 const old={id:'task1',version:9,status:'submitted',ordinal:1}
 assert.equal(newestAssistantTask(old,fresh,10,50),fresh)
})
test('only the newly recorded question and answer count as synchronized', () => {
 const old=[{id:1,role:'user',content:'问题'},{id:2,role:'assistant',content:'相同回复'}]
 const reply={answer:'相同回复',clientQuery:'问题',afterMessageId:2}
 assert.equal(hasRecordedReply(old,reply),false)
 assert.equal(hasRecordedReply([...old,{id:3,role:'user',content:'问题'},{id:4,role:'assistant',content:'相同回复'}],reply),true)
 assert.equal(hasRecordedReply([...old,{id:3,role:'user',content:'别的问题'},{id:4,role:'assistant',content:'相同回复'}],reply),false)
})


test('several answers missing from history stay between their preceding and following saved turns', () => {
  const messages = [{id: 1}, {id: 2}, {id: 3}, {id: 4}]
  const missing = [{id: 12, afterMessageId: 2}, {id: 11, afterMessageId: 2}, {id: 13, afterMessageId: 4}]
  const display = orderAssistantTurns(messages, missing).map(entry => entry.server ? 'saved-' + entry.server.id : 'local-' + entry.local.id)
  assert.deepEqual(display, ['saved-1', 'saved-2', 'local-11', 'local-12', 'saved-3', 'saved-4', 'local-13'])
  assert.deepEqual(messages.map(message => message.id), [1, 2, 3, 4])
})

test('a saved question without its matching adjacent answer cannot hide a locally received reply', () => {
  assert.equal(assistantTurnStored([{id: 3, role: 'user', content: '问题'}], '问题', '回复', 2), false)
  assert.equal(assistantTurnStored([{id: 3, role: 'user', content: '问题'}, {id: 4, role: 'user', content: '后来问题'}, {id: 5, role: 'assistant', content: '回复'}], '问题', '回复', 2), false)
  assert.equal(assistantTurnStored([{id: 3, role: 'user', content: '问题'}, {id: 4, role: 'assistant', content: '另一回复'}], '问题', '回复', 2), false)
})

test('task ordinal protects the current draft from a late old response in either direction', () => {
  const fresh = {id: 'new-task', version: 1, status: 'collecting', ordinal: 12}
  const delayed = {id: 'old-task', version: 99, status: 'submitted', ordinal: 11}
  assert.equal(newestAssistantTask(fresh, delayed, 99, 10), fresh)
  assert.equal(newestAssistantTask(delayed, fresh, 10, 99), fresh)
})


test('public knowledge sources stay compact for both countries while student facts remain expanded', () => {
  for (const country of ['Germany', 'Singapore']) {
    const card = {source_url: 'https://official.example/' + country}
    assert.equal(assistantCardLayout({facts_kind: 'public_knowledge'}, card), 'source')
    assert.equal(assistantCardLayout({facts_kind: 'student_record', intent: 'ask'}, card), 'fact')
    assert.equal(assistantCardLayout({intent: 'ask'}, card), 'source')
    assert.equal(assistantCardLayout({knowledge_keys: ['transport']}, card), 'source')
  }
  assert.equal(assistantCardLayout({intent: 'profile'}, {}), 'fact')
  assert.equal(assistantCardLayout({intent: 'ask'}, {}), 'fact')
})

test('long answers land at their beginning instead of scrolling down to source cards', () => {
  assert.equal(replyScrollTarget({followReply: true, responseTop: 500, scrollHeight: 1400, viewportHeight: 364}), 492)
  assert.equal(replyScrollTarget({followReply: true, responseTop: 500, scrollHeight: 2400, viewportHeight: 364}), 492)
})

test('a growing streamed reply never takes scrolling away from a student reading earlier messages', () => {
  assert.equal(replyScrollTarget({followReply: false, responseTop: 500, scrollHeight: 2400, viewportHeight: 364}), undefined)
  assert.equal(replyScrollTarget({followReply: true, responseTop: 500, scrollHeight: 700, viewportHeight: 364}), 336)
  assert.equal(replyScrollTarget({followReply: true, scrollHeight: 700, viewportHeight: 364}), 0)
})

test('reading controls distinguish an earlier message from the rest of a long current answer', () => {
  assert.equal(replyReadingAction({scrollTop: 20, responseTop: 500, scrollHeight: 1400, viewportHeight: 364}), 'latest')
  assert.equal(replyReadingAction({scrollTop: 492, responseTop: 500, scrollHeight: 1400, viewportHeight: 364}), 'continue')
  assert.equal(replyReadingAction({scrollTop: 1036, responseTop: 500, scrollHeight: 1400, viewportHeight: 364}), undefined)
  assert.equal(replyReadingAction({scrollTop: 0, scrollHeight: 1400, viewportHeight: 364}), undefined)
})


test('expanded references exclude the main source, duplicate URLs, and unsafe schemes', () => {
  assert.deepEqual(additionalOfficialSources({source_url: 'https://official.example/main', sources: [
    {title: 'main again', url: 'https://official.example/main'},
    {title: 'payment', url: 'https://official.example/payment'},
    {title: 'duplicate', url: 'https://official.example/payment'},
    {title: 'unsafe', url: 'javascript:alert(1)'},
  ]}), [{title: 'payment', url: 'https://official.example/payment'}])
})

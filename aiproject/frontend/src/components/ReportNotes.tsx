import {readableNotes} from '../lib/reportNotes'

export function ReportNotes({value}: {value: unknown}) {
  const notes = readableNotes(value)
  return notes.length
    ? <div style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{notes.join('\n\n')}</div>
    : <span className="muted">—</span>
}

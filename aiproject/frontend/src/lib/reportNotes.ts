export function readableNotes(value: unknown): string[] {
  if (typeof value === 'string') return value.trim() ? [value] : []
  if (Array.isArray(value)) return value.flatMap(readableNotes)
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    return readableNotes(record.items ?? record.text ?? record.content ?? record.description)
  }
  return []
}

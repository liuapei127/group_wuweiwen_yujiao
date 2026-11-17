export const studyStages: Record<string, string> = {
  preparatory: '预科', language: '语言培训', overseas: '海外院校', unspecified: '历史记录待核对',
}
export const studyStageOptions = Object.entries(studyStages)
  .filter(([value]) => value !== 'unspecified').map(([value, label]) => ({value, label}))

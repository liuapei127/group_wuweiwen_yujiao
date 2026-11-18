import {Typography} from 'antd'

// Split only at known field labels. Semicolons inside a field remain part of its value.
const portraitLabels = [
  '年龄','学历','国内范围','家庭经济状况','升学需求','就业需求','就业导向','入学能力',
  '留学意愿','政策关注度','移民需求','技能需求','语言能力','德语水平','家庭支持',
  '经济理性','学习态度','性别','核心需求','动手能力','逻辑思维',
]
const fieldStart = new RegExp('(?:^|[；;\\n])\\s*(' + portraitLabels.join('|') + ')[：:]\\s*', 'g')

export function ScreeningFinding({text}: {text: string}) {
  if (!text.startsWith('画像已记录')) return <Typography.Paragraph className="screening-note">{text}</Typography.Paragraph>
  const body = text.replace(/^画像已记录[：:\s]*/, '')
  const matches = [...body.matchAll(fieldStart)]
  if (!matches.length || matches[0].index !== 0) return <Typography.Paragraph className="screening-note">{text}</Typography.Paragraph>
  return <section className="screening-portrait" aria-label="已记录画像">
    <Typography.Text strong>已记录画像</Typography.Text>
    <dl>{matches.map((match, index) => <div key={match.index}>
      <dt>{match[1]}</dt>
      <dd>{body.slice(match.index! + match[0].length, matches[index + 1]?.index ?? body.length).trim()}</dd>
    </div>)}</dl>
  </section>
}

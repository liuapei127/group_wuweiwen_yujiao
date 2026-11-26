import {Component, type ReactNode} from 'react'
import {Button, Result, Space} from 'antd'

type Props = {children: ReactNode}
type State = {error: Error | null}

export class ErrorBoundary extends Component<Props, State> {
  state: State = {error: null}

  static getDerivedStateFromError(error: Error): State {
    return {error}
  }

  componentDidCatch(error: Error) {
    console.error('Unhandled render error:', error)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{minHeight: '60vh', display: 'grid', placeItems: 'center', padding: 24}}>
        <Result
          status="error"
          title="页面展示出现异常"
          subTitle="刚才的页面渲染未能完成，你可以先重试或刷新页面。"
          extra={
            <Space>
              <Button type="primary" onClick={() => this.setState({error: null})}>重试</Button>
              <Button onClick={() => window.location.reload()}>刷新页面</Button>
            </Space>
          }
        />
      </div>
    )
  }
}

import {StrictMode} from 'react'
import {createRoot} from 'react-dom/client'
import {BrowserRouter,useLocation} from 'react-router-dom'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {App as AntApp,ConfigProvider} from 'antd'
import zhCN from 'antd/locale/zh_CN'
import {AuthProvider} from './auth'
import App from './App'
import {Visitor} from './pages/Visitor'
import './styles.css'
import './visitor.css'

function Entry() {
  const {pathname} = useLocation()
  return /^\/website(?:\/(?:visitor|student))?\/?$/.test(pathname)
    ? <Visitor/>
    : <AuthProvider><App/></AuthProvider>
}
const cache=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:10000,refetchOnWindowFocus:false}}})
createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={cache}><ConfigProvider locale={zhCN} theme={{token:{colorPrimary:'#087f75',colorInfo:'#087f75',borderRadius:10,fontFamily:'Inter, "Microsoft YaHei", "PingFang SC", sans-serif',colorBgLayout:'#f3f6fa',controlHeight:38},components:{Menu:{darkItemBg:'#102436',darkSubMenuItemBg:'#102436',darkItemSelectedBg:'#214f5a',itemHeight:44},Card:{paddingLG:24},Table:{headerBg:'#f7f9fc',headerColor:'#536273'}}}}><AntApp><BrowserRouter><Entry/></BrowserRouter></AntApp></ConfigProvider></QueryClientProvider></StrictMode>)

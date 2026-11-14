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
createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={cache}><ConfigProvider locale={zhCN} theme={{token:{colorPrimary:'#0F766E',colorInfo:'#0369A1',colorSuccess:'#15803D',colorWarning:'#B45309',colorError:'#DC2626',colorText:'#14201D',colorTextSecondary:'#5F706A',colorBorder:'#E4EAE7',colorBorderSecondary:'#EFF3F1',colorBgLayout:'#F7F9F8',colorBgContainer:'#FFFFFF',borderRadius:10,borderRadiusLG:14,controlHeight:40,fontSize:14,lineHeight:1.6,fontFamily:'-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif'},components:{Menu:{itemHeight:42},Card:{paddingLG:24},Table:{headerBg:'#F7F9F8',headerColor:'#3C4B46',rowHoverBg:'#F0F8F6'},Button:{primaryShadow:'none',defaultShadow:'none'},Input:{activeShadow:'0 0 0 3px rgba(15,118,110,.12)'}}}}><AntApp><BrowserRouter><Entry/></BrowserRouter></AntApp></ConfigProvider></QueryClientProvider></StrictMode>)

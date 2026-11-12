import {defineConfig,devices} from '@playwright/test'
import {existsSync} from 'node:fs'

const externalURL=process.env.ENT_PORTAL_URL
const baseURL=(externalURL||'http://127.0.0.1:5173').replace(/\/$/,'')
const installedChrome=process.platform==='win32'&&[
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
].some(existsSync)
// Local fallback uses the installed browser with a fresh isolated test profile.
// CI remains reproducible with Playwright's explicitly installed Chromium.
const channel=process.env.ENT_E2E_CHANNEL||(!process.env.CI&&installedChrome?'chrome':undefined)
const browser={...devices['Desktop Chrome'],...(channel&&channel!=='chromium'?{channel}:{})}
export default defineConfig({
  testDir:'./e2e',fullyParallel:false,retries:0,workers:1,
  reporter:[['list'],['json',{outputFile:'test-results/results.json'}]],
  webServer:externalURL?undefined:{
    command:'npm run dev',url:baseURL,reuseExistingServer:!process.env.CI,timeout:120_000,
  },
  use:{baseURL,trace:'retain-on-failure',screenshot:'only-on-failure',locale:'zh-CN'},
  projects:[
    {name:'ui-smoke',testMatch:/smoke\.spec\.ts/,use:browser},
    {name:'portal-integration',testMatch:/portal\.spec\.ts/,use:browser},
    {name:'portal-ai',testMatch:/portal-ai\.spec\.ts/,use:browser},
  ],
  timeout:45_000,expect:{timeout:10000},
})

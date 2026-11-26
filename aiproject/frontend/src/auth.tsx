import {createContext, useCallback, useContext, useEffect, useState, type ReactNode} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {api, getToken, refreshSession, setToken, type Row} from './lib/api'
export interface User { id:number;username:string;real_name:string;role_id:number;role_code:string;role_name:string;department:string;contact_info:string;permissions:string[];student_ids:number[] }
interface Auth {user:User|null;loading:boolean;login:(username:string,password:string)=>Promise<void>;logout:()=>Promise<void>;reload:()=>Promise<void>;can:(permission:string)=>boolean}
const Context=createContext<Auth|null>(null)
export function AuthProvider({children}:{children:ReactNode}) {
  const [user,setUser]=useState<User|null>(null);const [loading,setLoading]=useState(true);const cache=useQueryClient()
  const clear=useCallback(()=>{setToken('');setUser(null);cache.clear()},[cache])
  const reload=useCallback(async()=>{if(!getToken() && !await refreshSession()){setLoading(false);return}try{setUser(await api<User>('/api/v1/auth/me'))}catch(e){if((e as Row).status===401)clear()}finally{setLoading(false)}},[clear])
  useEffect(()=>{let active=true;void (async()=>{if(!getToken() && !await refreshSession()){if(active)setLoading(false);return}try{const me=await api<User>('/api/v1/auth/me');if(active)setUser(me)}catch(e){if(active&&(e as Row).status===401)clear()}finally{if(active)setLoading(false)}})();const expired=()=>clear();window.addEventListener('ent-auth-expired',expired);const focus=()=>void reload();window.addEventListener('focus',focus);return()=>{active=false;window.removeEventListener('ent-auth-expired',expired);window.removeEventListener('focus',focus);}},[clear,reload])
  const login=async(username:string,password:string)=>{const r=await api<{access_token:string;user:User}>('/api/v1/auth/login',{method:'POST',body:{username,password}});cache.clear();setToken(r.access_token);setUser(r.user)}
  const logout=async()=>{try{await api('/api/v1/auth/logout',{method:'POST'})}finally{clear()}}
  return <Context.Provider value={{user,loading,login,logout,reload,can:p=>Boolean(user?.permissions.includes(p))}}>{children}</Context.Provider>
}
export function useAuth(){const value=useContext(Context);if(!value)throw new Error('缺少登录上下文');return value}

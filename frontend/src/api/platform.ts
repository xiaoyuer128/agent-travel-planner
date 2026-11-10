import type {Session,Preferences} from '../types/chat';
export interface Profile {departure_city?:string;budget?:number;num_travelers?:number;interests?:string[];pace?:string;transport?:string;walking?:string;needs?:string}
export interface User {id:string;email:string;name:string;profile:Profile}
export interface City {city:string;spots:string[];tags:string[];seasonal:boolean;description:string}
export interface Spot {name:string;subtitle:string;tag:string;image?:string;source:string;location?:string;seasonal:boolean;city?:string;poi_id?:string}
export interface Folder {id:string;name:string}
export interface Favorite {id:string;folder_id:string;kind:string;city:string;name:string;target:string;image?:string}
export interface Post {id:string;title:string;body:string;city:string;travel_date?:string;visibility:string;status:string;images:string[];author?:string;created:number}
export async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{
 const r=await fetch('/api'+path,{method,credentials:'same-origin',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 if(!r.ok){const value=await r.json().catch(()=>null);throw new Error(typeof value?.detail==='string'?value.detail:`请求失败（${r.status}），请检查输入后重试`)}
 return r.json();
}
export const message=(s:Session,text:string,patch?:Preferences,generate=true)=>api<Session>(`/chat/sessions/${s.id}/messages`,'POST',{message:text,revision:s.revision,patch,generate});
export function uploadImage(file:File,onProgress:(percent:number)=>void):Promise<{id:string;url:string}>{
 return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/uploads');xhr.withCredentials=true;
 xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.round(e.loaded/e.total*100))};
 xhr.onload=()=>{let value;try{value=JSON.parse(xhr.responseText)}catch{reject(new Error('上传失败，请重试'));return}if(xhr.status>=200&&xhr.status<300)resolve(value);else reject(new Error(value.detail||'上传失败'))};
 xhr.onerror=()=>reject(new Error('图片上传网络异常，请重新选择重试'));xhr.send(file);
 });
}

import type {Session,Preferences} from '../types/chat';
import {api} from './platform';
export interface RunEvent {event:string;data:Record<string,unknown>}
export class RunCancelled extends Error{}
class TerminalError extends Error{}
async function checked(response:Response){if(!response.ok){const data=await response.json().catch(()=>null);throw new TerminalError(typeof data?.detail==='string'?data.detail:'生成服务暂不可用')}return response}

export async function streamMessage(session:Session,text:string,patch:Preferences|undefined,generate:boolean,onEvent:(event:RunEvent)=>void,onStarted:(id:string)=>void,action='auto'):Promise<Session>{
 const key=crypto.randomUUID();const body=JSON.stringify({message:text,patch,generate,action,revision:session.revision});let job:{id:string}|undefined;
 for(let attempt=0;attempt<2&&!job;attempt++){
  try{job=await(await checked(await fetch(`/api/chat/sessions/${session.id}/runs`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Idempotency-Key':key},body}))).json()}
  catch(e){if(e instanceof TerminalError||attempt===1)throw e;await new Promise(r=>setTimeout(r,600))}
 }
 if(!job)throw new Error('无法创建生成任务');const id=job.id;onStarted(id);let cursor=0;
 for(let attempt=0;attempt<3;attempt++){
  try{
   const response=await checked(await fetch(`/api/chat/runs/${id}/events?after=${cursor}`,{credentials:'same-origin'}));
   if(!response.body)throw new Error('浏览器不支持流式响应');const reader=response.body.getReader();const decoder=new TextDecoder();let buffer='';
   try{while(true){const chunk=await reader.read();if(chunk.done)break;buffer+=decoder.decode(chunk.value,{stream:true});let boundary;
    while((boundary=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);if(frame.startsWith(':'))continue;
     const lines=frame.split('\n');const event=lines.find(l=>l.startsWith('event:'))?.slice(6).trim();const seq=Number(lines.find(l=>l.startsWith('id:'))?.slice(3).trim());const raw=lines.filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');
     if(!event||!raw||seq<=cursor)continue;const data=JSON.parse(raw);cursor=seq;onEvent({event,data});
     if(event==='done')return data.session as Session;
     if(event==='cancelled')throw new RunCancelled(data.message||'已停止生成');
     if(event==='error')throw new TerminalError(data.message||'生成失败');
    }
   }}finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
   const status=await api<{status:string;session?:Session}>(`/chat/runs/${id}`);
   if(status.status==='completed'&&status.session)return status.session;
   if(status.status==='cancelled')throw new RunCancelled('已停止生成');
   throw new Error('生成连接中断');
  }catch(e){
   if(e instanceof RunCancelled||e instanceof TerminalError||attempt===2)throw e;
   onEvent({event:'progress',data:{stage:'reconnecting',label:'连接中断，正在接续同一任务…'}});
   await new Promise(r=>setTimeout(r,700*(attempt+1)));
  }
 }
 throw new Error('连接中断，请刷新查看任务结果后重试');
}

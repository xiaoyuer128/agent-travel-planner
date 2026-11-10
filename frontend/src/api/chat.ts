import type { Session, SessionItem, Preferences } from '../types/chat';
async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api/chat${path}`, body === undefined ? undefined : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  if (!r.ok) {
    const value = await r.json().catch(() => null);
    throw new Error(r.status === 409 ? '会话已在其他窗口更新，请刷新后再发送。' :
      typeof value?.detail === 'string' ? value.detail : `请求失败（${r.status}），请检查输入和后端服务。`);
  }
  return r.json();
}
export const listSessions = () => call<SessionItem[]>('/sessions');
export const newSession = () => call<Session>('/sessions', {});
export const loadSession = (id: string) => call<Session>(`/sessions/${id}`);
export const sendTurn = (s: Session, message: string, patch?: Preferences, action = 'auto') =>
  call<Session>(`/sessions/${s.id}/messages`, {message, revision: s.revision, patch, action});
export const restorePlan = (s: Session, version: number) =>
  call<Session>(`/sessions/${s.id}/restore/${version}`, {message: '恢复方案', revision: s.revision});

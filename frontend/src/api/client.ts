// API 客户端 —— 统一封装对 FastAPI 后端的调用
import type { PlanRequest, TravelPlanState } from "../types/plan";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`请求失败 ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

/** 提交行程规划，返回完整 TravelPlanState（含航班/酒店/行程/预算/RAG 上下文） */
export function planFull(data: PlanRequest): Promise<TravelPlanState> {
  return request<TravelPlanState>("/plan/full", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/** 健康检查 */
export function health(): Promise<{ status: string; service: string; agents: number }> {
  return request("/health");
}
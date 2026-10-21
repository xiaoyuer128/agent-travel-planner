# 多 Agent 智能旅游行程规划助手（Python 后端）

基于多 Agent 协作的智能自由行行程规划系统：用户只需给出预算、出发地、日期、旅行风格（可选目的地），系统自动完成目的地推荐、航班/酒店/活动并行搜索与预算控制，输出一套结构化行程方案。

> 全程 Mock 优先、零依赖可运行；真实 LLM / RAG 组件（BGE-M3 + Milvus）通过环境变量按需启用。

## 核心特性

- **6-Agent 协同编排**：偏好 → 目的地 → [航班 + 酒店 + 活动 并行] → 预算，采用 `Pipeline + 并行 + 预算循环` 三层编排架构
- **异步并行搜索**：航班/酒店/活动三 Agent 通过 `asyncio.gather` 并发执行，显著降低端到端延迟
- **预算控制循环**：渐进式降级（最多 3 轮），必要时自动降低酒店/活动档次，避免超预算与无限循环
- **RAG 检索增强**：目的地攻略/景点资料向量化检索，为各 Agent 补充真实上下文、减少模型幻觉
- **任意城市自由输入**：目的地支持任意城市，未内置攻略的城市自动跳过 RAG、回落到通用模板
- **前后端分离**：REST API + Vue3 前端（本目录为后端，前端见仓库根目录 `frontend/`）

## 架构

```
用户输入 → PreferenceAgent → DestinationAgent
         → [ FlightAgent + HotelAgent + ActivityAgent (asyncio.gather 并行) ]
         → BudgetAgent (预算校验)
         ↓ (超预算则循环降级)
         输出最终行程
```

## 技术栈

- **Python 3.10+**
- **FastAPI** — REST API
- **Pydantic v2** — 数据模型与校验
- **asyncio** — 并行 Agent 执行
- **loguru** — 日志
- **pytest** — 单元测试
- **RAG** — BGE-M3 向量化 + Milvus 向量库（默认走零依赖 Mock：字符 n-gram 向量化 + 内存检索）

> 前端：**Vue 3 + TypeScript + Vite + Element Plus**（位于 `../frontend/`）。旧版 Streamlit 前端保留于 `ui/`，可选使用。

## 快速开始

### 后端

```bash
# 安装依赖
pip install -r requirements.txt

# 方式一：CLI 演示（默认 Mock 模式，零配置）
python main.py
python main.py --budget 15000 --departure 上海 --start 2026-06-01 --end 2026-06-07 --destination 东京

# 方式二：启动 REST API（http://localhost:8000）
python -m api.app
```

### 前端（Vue3）

```bash
cd ../frontend
npm install
npm run dev        # http://localhost:5173（默认代理 /api → localhost:8000）
npm run build      # 类型检查 + 生产构建
```

### 运行测试

```bash
python -m pytest tests/ -v
```

## 目录结构（python/）

| 目录 / 文件       | 说明                                              |
| ----------------- | ------------------------------------------------- |
| `agents/`         | 6 个 Agent 实现 + 基类（模板方法模式）            |
| `orchestrator/`   | Pipeline 编排 + 并行执行 + 预算循环               |
| `models/`         | Pydantic 数据模型（Agent 间流转的 state）         |
| `rag/`            | RAG 知识库（Embedding 抽象 + 向量库抽象 + 攻略文档 + 检索工具） |
| `api/`            | FastAPI REST API                                  |
| `config/`         | 配置管理（settings）                              |
| `llm_client.py`   | LLM 调用客户端（`chat_json`）                     |
| `tests/`          | 单元测试                                          |
| `main.py`         | CLI 入口                                          |
| `ui/`             | 旧版 Streamlit 前端（可选）                       |

## API 端点

| 方法 | 路径            | 说明                                       |
| ---- | --------------- | ------------------------------------------ |
| GET  | `/api/health`   | 健康检查                                   |
| POST | `/api/plan`     | 快速规划（返回摘要）                       |
| POST | `/api/plan/full`| 完整规划（返回航班/酒店/行程/预算/RAG 全文）|

## 环境变量

复制 `.env.example` 为 `.env` 进行配置。默认 Mock 模式无需任何配置即可运行。

| 变量                  | 默认值                      | 说明                                              |
| --------------------- | --------------------------- | ------------------------------------------------- |
| `LLM_PROVIDER`        | `mock`                      | `mock` / 真实 LLM provider                        |
| `LLM_API_KEY`         | —                           | LLM API Key                                       |
| `LLM_MODEL`           | —                           | 模型名                                            |
| `LLM_BASE_URL`        | —                           | LLM 接口地址                                      |
| `RAG_EMBEDDING`       | `mock`                      | `mock`（字符 n-gram）/ `bge-m3`（需 FlagEmbedding）|
| `RAG_STORE`           | `memory`                    | `memory`（内存检索）/ `milvus`（需 Milvus 服务）  |
| `RAG_TOP_K`           | `3`                         | Top-K 检索片段数                                   |
| `MILVUS_URI`          | `http://localhost:19530`    | Milvus 服务地址                                    |
| `MILVUS_COLLECTION`   | `travel_guides`             | Milvus 集合名                                      |
# Python 后端

当前网站使用 **FastAPI + LangGraph + DeepSeek / Mock**，并包含账户、国内推荐、收藏、图片、内容审核与行程分享。DeepSeek模式还通过JSON生成分项费用估算，由后端校验并汇总。

完整的功能说明、安装启动、环境变量、管理员配置、架构和测试步骤统一维护在[仓库 README](../README.md)，请以该文档为准。

## 常用命令

在本目录安装 `requirements.txt` 后：

```bash
python -m uvicorn api.app:app --host 127.0.0.1 --port 18000
python -m pytest tests -q
python manage_admin.py 你已注册的邮箱
```

Windows 虚拟环境使用 `.venv\Scripts\python`，macOS / Linux 使用 `.venv/bin/python`。

默认数据存储在 `data/`，配置在 `.env`，均不提交 Git。复制 `.env.example` 后可以使用 Mock 模式运行，填入自己的密钥再切换 DeepSeek。

`main.py`、`agents/`、`orchestrator/` 和 `ui/` 是保留的旧版 CLI / Pipeline / Streamlit 实现，不是当前网站的默认入口。

费用生成入口为`chat/deepseek.py`中的`estimate`，Schema与缺失字段补足位于`chat/estimates.py`，总预算由`chat/planner.py`计算。模型费用为AI估算，页面展示依据与补足说明。

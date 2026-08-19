# myAgent

基于 [deepagents](https://github.com/langchain-ai/deepagents) / LangGraph 构建的智能助手后端，通过 FastAPI 提供 SSE 流式对话接口。

## 特性

- **流式对话**：`POST /api/chat` 以 SSE 推送 `start / token / tool_call / tool_result / done / error` 事件，前端可实时展示模型输出与工具调用过程。
- **多轮会话**：使用 `AsyncSqliteSaver` 作为 checkpointer，按 `thread_id` 持久化对话状态，重启进程不丢失上下文。
- **子智能体**：内置 `research-agent`，通过 Tavily 联网搜索协助解决时效性问题，主 agent 可按需委派任务。
- **文件系统能力**：基于 `FilesystemBackend` 的虚拟根目录（`agent_files/`），agent 可读写文件但无法越权访问宿主机其他路径。
- **可扩展工具**：工具定义在 `app/agent/tools/`，例如 `get_current_time`、`internet_search`，以及一个可选的 NAS（SFTP）文件保存工具。

## 项目结构

```
app/
├── agent/
│   ├── client.py          # OpenAI 兼容模型客户端构建
│   ├── mainAgent.py        # 主 agent 图的构建，以及 CLI 调试入口
│   ├── prompts/            # 系统提示词
│   ├── states/              # LangGraph 状态定义（AgentState）
│   ├── subAgent/            # 子智能体（research-agent）
│   └── tools/                # 工具函数（时间、联网搜索、NAS 保存等）
├── db/                     # SQLAlchemy engine / session
├── model/                  # ORM 模型
├── repository/             # 数据访问层
├── route/                  # FastAPI 路由（HTTP 层）
├── schema/                 # 请求 / 响应 Pydantic 模型
└── service/                # 业务逻辑，负责把 LangGraph 事件转成 ChatEvent
main.py                     # FastAPI 应用入口
```

## 快速开始

### 依赖

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)

### 安装

```bash
uv sync
```

### 配置环境变量

复制 `.env.example` 为 `.env` 并填入真实值：

```bash
cp .env.example .env
```

| 变量 | 说明 |
| --- | --- |
| `OPENAI_BASE_URL` | OpenAI 兼容模型端点 |
| `OPENAI_API_KEY` | 模型服务的 API Key |
| `AGENT_MODEL` | 使用的模型名称 |
| `TAVILY_API_KEY` | [Tavily](https://app.tavily.com) 联网搜索 API Key |
| `nas_host` / `nas_username` / `nas_password` | NAS SFTP 配置（`save_md2nas` 工具使用，当前默认关闭） |
| `CHECKPOINT_DB` | LangGraph checkpoint 数据库路径，默认 `checkpoints.db` |
| `CORS_ORIGINS` | 允许的跨域来源，逗号分隔，默认 `*` |
| `DATABASE_URL` | 业务数据库连接串，默认 `sqlite:///./myagent.db` |

### 启动服务

```bash
uv run uvicorn main:app --reload
```

服务启动后访问 `http://127.0.0.1:8000/health` 确认存活。

### 命令行调试 agent

不经过 HTTP，直接在终端里和 agent 对话（使用内存 checkpointer，进程退出即丢失上下文）：

```bash
uv run python -m app.agent.mainAgent
```

## API

### `POST /api/chat`

请求体：

```json
{
  "message": "你好",
  "thread_id": null
}
```

- `message`：用户输入，1~8000 字符。
- `thread_id`：会话 id，不传则由服务端新建并通过 `start` 事件返回。

响应为 SSE 流，每条事件的 `data` 是一个 `ChatEvent` JSON。

### `GET /api/chat/{thread_id}`

读取指定会话的历史消息（仅返回用户 / 助手可读消息，不含工具调用细节）。

## 技术栈

FastAPI · LangGraph / deepagents · LangChain (OpenAI 兼容) · SQLAlchemy · SQLite (langgraph-checkpoint-sqlite) · Tavily · Paramiko (SFTP)

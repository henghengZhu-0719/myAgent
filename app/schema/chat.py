"""对话接口的请求 / 响应模型。

HTTP 边界上的校验都在这里做：AgentState 是 TypedDict，运行时不校验任何东西，
不在这层挡住空消息、超长输入，脏数据会一路走到模型调用。
"""

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/chat 的请求体。"""

    message: str = Field(min_length=1, max_length=8000, description="用户输入")
    thread_id: str | None = Field(
        default=None,
        description="会话 id。不传则服务端新建一轮，通过 start 事件返回。",
    )


EventType = Literal["start", "token", "tool_call", "tool_result", "done", "error"]


class ChatEvent(BaseModel):
    """SSE 推给前端的单个事件。

    字段按 type 取用：
      start       -> thread_id
      token       -> text（模型吐出的增量文本，需要前端自己拼接）
      tool_call   -> tool、args、agent
      tool_result -> tool、text、agent
      done        -> elapsed
      error       -> text
    """

    type: EventType
    text: str | None = None
    thread_id: str | None = None
    tool: str | None = None
    args: dict | None = None
    # 事件来自哪个 agent：主 agent 为 None，subagent 为其名字
    agent: str | None = None
    elapsed: float | None = None


class ChatMessage(BaseModel):
    """历史消息，GET /api/chat/{thread_id} 用。"""

    role: Literal["user", "assistant"]
    content: str


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[ChatMessage]
 
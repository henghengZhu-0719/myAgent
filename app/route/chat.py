"""对话相关的 HTTP 接口。这层只管 HTTP，逻辑都在 app/service。"""

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.schema.chat import ChatRequest, HistoryResponse
from app.service.chat import get_history, stream_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
async def chat(request: Request, body: ChatRequest) -> EventSourceResponse:
    """SSE 流式对话。

    事件的 data 是 ChatEvent 的 JSON，type 字段区分种类：
    start / token / tool_call / tool_result / done / error。
    """
    agent = request.app.state.agent

    async def events():
        async for event in stream_chat(agent, body.message, body.thread_id):
            # 客户端关掉页面就没必要继续跑了
            if await request.is_disconnected():
                break
            yield {"event": event.type, "data": event.model_dump_json(exclude_none=True)}

    return EventSourceResponse(events())


@router.get("/{thread_id}", response_model=HistoryResponse)
async def history(request: Request, thread_id: str) -> HistoryResponse:
    """读回某轮会话的对话记录。thread_id 不存在时返回空列表。"""
    messages = await get_history(request.app.state.agent, thread_id)
    return HistoryResponse(thread_id=thread_id, messages=messages)

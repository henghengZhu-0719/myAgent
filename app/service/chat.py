"""对话业务逻辑：把 LangGraph 的流式事件翻译成前端能吃的 ChatEvent。

这一层不认识 FastAPI，只吐 ChatEvent，方便单测。
"""

import time
import uuid
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from app.schema.chat import ChatEvent, ChatMessage

# 工具返回内容推给前端时截断，避免一次搜索的原文把 SSE 撑爆
MAX_TOOL_RESULT = 500


def new_thread_id() -> str:
    """服务端生成会话 id，同时作为 langgraph 的 thread_id。"""
    return uuid.uuid4().hex


def _agent_name(namespace: tuple[str, ...]) -> str | None:
    """namespace 非空说明事件来自 subagent，取出它的名字。"""
    if not namespace:
        return None
    return namespace[-1].split(":")[0]


async def stream_chat(
    agent: CompiledStateGraph,
    message: str,
    thread_id: str | None = None,
) -> AsyncIterator[ChatEvent]:
    """跑一轮对话，逐事件 yield。

    thread_id 为空时新建一轮，并通过第一个 start 事件把 id 告诉前端。
    """
    thread_id = thread_id or new_thread_id()
    config = {"configurable": {"thread_id": thread_id}}
    started = time.perf_counter()

    yield ChatEvent(type="start", thread_id=thread_id)

    try:
        # messages 拿逐 token 增量，updates 拿节点跑完的结果；
        # subgraphs=True 才能看到 research-agent 内部的动静
        async for namespace, mode, payload in agent.astream(
            {"messages": [HumanMessage(message)]},
            config,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            agent_name = _agent_name(namespace)

            if mode == "messages":
                chunk, _meta = payload
                if isinstance(chunk, AIMessageChunk) and chunk.text:
                    yield ChatEvent(type="token", text=chunk.text, agent=agent_name)

            elif mode == "updates":
                for update in (payload or {}).values():
                    if not isinstance(update, dict):
                        continue
                    for msg in update.get("messages", []) or []:
                        if isinstance(msg, ToolMessage):
                            text = str(msg.content)
                            if len(text) > MAX_TOOL_RESULT:
                                text = text[:MAX_TOOL_RESULT] + "…"
                            yield ChatEvent(
                                type="tool_result",
                                tool=msg.name,
                                text=text,
                                agent=agent_name,
                            )
                        elif isinstance(msg, AIMessage):
                            # 参数要等整条消息落地才完整，所以在 updates 里发
                            for call in msg.tool_calls or []:
                                yield ChatEvent(
                                    type="tool_call",
                                    tool=call["name"],
                                    args=call["args"],
                                    agent=agent_name,
                                )

    except Exception as e:  # noqa: BLE001 - 异常要变成 SSE 事件，不能让连接直接断
        yield ChatEvent(type="error", text=f"{type(e).__name__}: {e}")
        return

    yield ChatEvent(type="done", elapsed=round(time.perf_counter() - started, 2))


async def get_history(
    agent: CompiledStateGraph,
    thread_id: str,
) -> list[ChatMessage]:
    """从 checkpointer 里读回这轮对话的用户/助手消息。

    工具消息和空内容的 AIMessage（只带 tool_calls 的那种）不返回，
    前端要的是可读的对话记录。
    """
    snapshot = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    history: list[ChatMessage] = []
    for msg in snapshot.values.get("messages", []):
        if isinstance(msg, HumanMessage):
            history.append(ChatMessage(role="user", content=str(msg.content)))
        elif isinstance(msg, AIMessage) and msg.text:
            history.append(ChatMessage(role="assistant", content=msg.text))
    return history

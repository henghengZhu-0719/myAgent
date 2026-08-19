from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from deepagents import create_deep_agent

from .backend import build_backend
from .client import build_model
from .prompts.prompt import SYSTEM_PROMPT
from .states import AgentState
from .subAgent import image_subagent, research_subagent
from .tools import get_current_time

TOOLS = [get_current_time,]
SUBAGENTS = [research_subagent, image_subagent]


def build_agent(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """构建并编译 agent 图。checkpointer 传入后即可按 thread_id 续聊。"""
    return create_deep_agent(
        model=build_model(),
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        state_schema=AgentState,
        subagents=SUBAGENTS,
        backend=build_backend(),
        checkpointer=checkpointer,
    )


def _cli() -> None:
    """命令行里跟 agent 对话，调试用。

    因为本文件用了相对 import，必须以模块方式运行：
        uv run python -m app.agent.mainAgent
    """
    import sys
    import time

    from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
    from langgraph.checkpoint.memory import InMemorySaver

    # 内存 checkpointer：进程内多轮对话共享上下文，退出即丢
    agent = build_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "cli-debug"}}

    def out(text: str = "", end: str = "\n") -> None:
        """立刻刷到终端，不然流式输出会卡在缓冲区里看不见。"""
        print(text, end=end, flush=True)

    print("agent 已就绪，输入内容开始对话（quit / Ctrl-C 退出）\n")
    while True:
        try:
            user_input = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input in {"quit", "exit", "q"}:
            break

        started = time.perf_counter()
        streaming = False  # 当前是否正在逐字打印模型输出

        # messages 模式拿逐 token 的增量，updates 模式拿每个节点跑完的结果；
        # subgraphs=True 才能看到 research-agent 这类 subagent 内部的动静。
        for namespace, mode, payload in agent.stream(
            {"messages": [HumanMessage(user_input)]},
            config,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            # namespace 非空表示事件来自 subagent，缩进区分层级
            indent = "    " * len(namespace)
            where = f"[{namespace[-1].split(':')[0]}] " if namespace else ""

            if mode == "messages":
                chunk, _meta = payload
                if not isinstance(chunk, AIMessageChunk):
                    continue
                text = chunk.text
                if text:
                    if not streaming:
                        out(f"\n{indent}{where}agent > ", end="")
                        streaming = True
                    out(text, end="")
                # 工具名是分片到达的，出现名字时说明模型开始拼调用了
                for call in chunk.tool_call_chunks or []:
                    if call.get("name"):
                        if streaming:
                            out()
                            streaming = False
                        out(f"{indent}  🔧 {call['name']} …")

            elif mode == "updates":
                for node, update in (payload or {}).items():
                    if not isinstance(update, dict):
                        continue
                    for msg in update.get("messages", []) or []:
                        if isinstance(msg, ToolMessage): 
                            if streaming:
                                out() 
                                streaming = False
                            body = " ".join(str(msg.content).split())
                            if len(body) > 300:
                                body = body[:300] + f"…（共 {len(str(msg.content))} 字符）"
                            out(f"{indent}  ↩︎ {msg.name}: {body}")
                        elif getattr(msg, "tool_calls", None):
                            # 参数要等整条消息落地才完整，这里补印一次
                            for call in msg.tool_calls:
                                out(f"{indent}     ↳ 参数 {call['args']}")
                    if node not in {"model", "tools"}:
                        out(f"{indent}  · 节点 {node} 完成")

        if streaming:
            out()

        # 看看自定义 state 字段有没有被工具写进去
        saved = agent.get_state(config).values.get("saved_files")
        if saved:
            out(f"\n[state.saved_files] {saved}")
        out(f"\n（耗时 {time.perf_counter() - started:.1f}s）\n")
        sys.stdout.flush()


if __name__ == "__main__":
    _cli()

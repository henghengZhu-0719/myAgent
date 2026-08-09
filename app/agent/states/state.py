"""Agent 的状态定义（StateGraph 的 state schema）。

deepagents 自带的 `DeepAgentState` 已经包含：
  - messages：对话历史，使用 DeltaChannel 增量存储，避免 checkpoint 随轮次平方增长
  - todos / files 等由中间件写入的字段

这里在其之上追加本项目自己的业务字段。所有字段都必须是 `NotRequired`，
否则调用 `graph.invoke({"messages": [...]})` 时会因为缺字段而报错。
"""

from typing import Annotated, Any, NotRequired

from deepagents import DeepAgentState


def keep_last(old: Any, new: Any) -> Any:
    """reducer：后写入的值覆盖旧值，节点返回 None 表示本次不更新。"""
    return old if new is None else new


def append_paths(old: list[str] | None, new: list[str] | str | None) -> list[str]:
    """reducer：把新文件路径追加到列表里，支持传单个字符串。"""
    result = list(old or [])
    if new is None:
        return result
    if isinstance(new, str):
        result.append(new)
    else:
        result.extend(new)
    return result


class AgentState(DeepAgentState):
    """本项目 agent 的运行时状态。"""

    # 当前会话 / 用户标识，供工具和日志使用
    thread_id: NotRequired[Annotated[str | None, keep_last]]
    user_id: NotRequired[Annotated[str | None, keep_last]]

    # 本轮请求中 agent 落到 NAS 的文件路径，方便接口层回传给前端
    saved_files: NotRequired[Annotated[list[str], append_paths]]


__all__ = ["AgentState", "keep_last", "append_paths"]

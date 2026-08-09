import os
import time
from typing import Annotated

import paramiko
from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

load_dotenv()


@tool
def get_current_time():
    """获取服务器当前本地时间"""
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "current_time": current_time
    }

# @tool
# def save_md2nas(
#     filename: str,
#     content: str,
#     tool_call_id: Annotated[str, InjectedToolCallId],
# ) -> Command:
#     """
#     将 Markdown 文件通过 SFTP 保存到 NAS。
#     """
#     host = os.getenv("nas_host")
#     port = 21
#     username = os.getenv("nas_username")
#     password = os.getenv("nas_password")

#     remote_path = f"/vol1/1000/zhuyq/派乐多/ai_file/{filename}"

#     try:
#         transport = paramiko.Transport((host, port))
#         transport.connect(
#             username=username,
#             password=password
#         )

#         sftp = paramiko.SFTPClient.from_transport(transport)

#         with sftp.open(remote_path, "w") as f:
#             f.write(content)

#         sftp.close()
#         transport.close()

#     except Exception as e:
#         # 失败时只回消息，不写 saved_files
#         return _reply(tool_call_id, f"保存失败：{e}")

#     # 成功：回消息给模型，同时把路径追加进 state.saved_files
#     return _reply(
#         tool_call_id,
#         f"文件保存成功：{remote_path}",
#         saved_files=[remote_path],
#     )


# def _reply(tool_call_id: str, text: str, **updates) -> Command:
#     """把工具结果包成 Command：既回 ToolMessage，又顺带更新 state 字段。

#     工具一旦返回 Command，就必须自己造 ToolMessage —— 否则这次 tool_call
#     没有对应的响应，下一轮请求会被模型端判为非法。
#     """
#     return Command(
#         update={
#             "messages": [ToolMessage(text, tool_call_id=tool_call_id)],
#             **updates,
#         }
#     )
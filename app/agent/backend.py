"""agent 落盘用的 FilesystemBackend 构建逻辑。

单独拆出来是因为 mainAgent（构建主 agent 图）和 tools（比如画图工具要把
生成的图片写进同一个目录）都需要同一份 FILES_DIR / backend 逻辑，避免
两处各算一遍虚拟根目录、算法不一致导致文件散落在不同地方。
"""

import os
from pathlib import Path

from deepagents.backends import FilesystemBackend

# agent 的文件都落在这个目录下。默认是项目根的 agent_files/
FILES_DIR = Path(os.getenv("AGENT_FILES_DIR", Path(__file__).resolve().parents[2] / "agent_files"))


def build_backend() -> FilesystemBackend:
    """真写磁盘的 backend。

    不传 backend 时 deepagents 用的是 StateBackend —— 文件只存在 state["files"]
    这个 channel 里，磁盘上找不到，进程退出就没了。
    virtual_mode=True 把 FILES_DIR 当成虚拟根：模型看到的 /a.md 实际落在
    FILES_DIR/a.md，它也跳不出这个目录。
    """
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    return FilesystemBackend(root_dir=FILES_DIR, virtual_mode=True)

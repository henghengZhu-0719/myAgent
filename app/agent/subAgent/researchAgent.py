import os
from typing import Literal

from deepagents import create_deep_agent
from ..client import build_model
from ..prompts.prompt import RESEARCH_PROMPT 
from ..states import AgentState
from ..tools import get_current_time, internet_search

TOOLS = [get_current_time, internet_search]

research_subagent = {
    "name": "research-agent",
    "description": "使用检索网页工具去帮助用户解决问题",
    "system_prompt": RESEARCH_PROMPT,
    "tools": TOOLS,
}

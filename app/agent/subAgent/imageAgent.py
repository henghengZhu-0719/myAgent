from ..prompts.prompt import IMAGE_PROMPT
from ..states import AgentState
from ..tools import generate_image

TOOLS = [generate_image]

image_subagent = {
    "name": "image-agent",
    "description": "使用画图工具根据文字描述生成图片",
    "system_prompt": IMAGE_PROMPT,
    "tools": TOOLS,
}

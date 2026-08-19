from ..prompts.prompt import PDF_PROMPT
from ..tools import inspect_box_pdf, split_box_pdf

TOOLS = [inspect_box_pdf, split_box_pdf]

pdf_subagent = {
    "name": "pdf-agent",
    "description": "解析礼盒刀版 PDF，按每个面（外盒、内盒）切分成单独的图片",
    "system_prompt": PDF_PROMPT,
    "tools": TOOLS,
}

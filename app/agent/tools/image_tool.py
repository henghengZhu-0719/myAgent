import base64
import os
import re
import uuid
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from langchain_core.tools import tool
from openai import OpenAI

from app.agent.backend import build_backend

load_dotenv()

IMAGE_MODEL = os.getenv("AGENT_IMAGE_MODEL", "gpt-image-2")


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    """延迟创建 OpenAI 客户端，复用聊天模型的同一个兼容端点。"""
    return OpenAI(
        base_url=os.environ["OPENAI_BASE_URL"],
        api_key=os.environ["OPENAI_API_KEY"],
    )


def _slugify(prompt: str) -> str:
    """把提示词裁成一段能当文件名的短字符串。"""
    slug = re.sub(r"[^\w一-鿿-]+", "_", prompt.strip()).strip("_")[:40]
    return slug or "image"


@tool
def generate_image(
    prompt: str,
    size: Literal["1024x1024", "1536x1024", "1024x1536"] = "1024x1024",
) -> dict:
    """根据文字描述生成一张图片，并保存到 agent 的文件系统中。

    Args:
        prompt: 图片内容的详细描述，越具体效果越好，建议包含风格、构图、色彩等细节。
        size: 图片尺寸。正方形 1024x1024 / 横向 1536x1024 / 纵向 1024x1536。
    """
    result = _client().images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size=size,
        n=1,
    )
    b64 = result.data[0].b64_json
    if not b64:
        return {"error": "模型没有返回图片数据"}

    file_path = f"/images/{_slugify(prompt)}_{uuid.uuid4().hex[:8]}.png"
    uploaded = build_backend().upload_files([(file_path, base64.b64decode(b64))])[0]
    if uploaded.error:
        return {"error": uploaded.error}

    return {"path": file_path}

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

MODEL = os.getenv("AGENT_MODEL")


def build_model() -> ChatOpenAI:
    """OpenAI 兼容端点的模型实例。base_url / api_key 从 .env 读取。"""
    return ChatOpenAI(
        model=MODEL,
        base_url=os.environ["OPENAI_BASE_URL"],
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=120,
        max_retries=2,
    )

import os
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()


@lru_cache(maxsize=1)
def _client() -> TavilyClient:
    """延迟创建 Tavily 客户端。

    不在模块顶层建实例：那样 import 本模块的瞬间就要求 TAVILY_API_KEY 存在，
    整个应用的启动会依赖 import 顺序（谁先调 load_dotenv）。
    """
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def internet_search(
    query: str,
    max_results: int = 2,
    topic: Literal["general", "news", "finance"] = "finance",
    include_raw_content: bool = False,
):
    """联网搜索。需要时效性信息、或本地知识不足以回答时使用。

    Args:
        query: 搜索关键词。
        max_results: 返回的结果条数。
        topic: 搜索领域，general / news / finance。
        include_raw_content: 是否返回网页正文全文，会显著增加返回长度。
    """
    return _client().search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

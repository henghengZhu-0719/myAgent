"""FastAPI 入口。

    uv run uvicorn main:app --reload
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.mainAgent import build_agent
from app.route import chat_router

load_dotenv()

CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", "checkpoints.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """进程启动时建一次 agent，整个生命周期复用。

    agent 的构建要拉起模型客户端和一堆 middleware（约 0.5s），
    放进请求里等于每次都付一遍。
    checkpointer 用 SqliteSaver 而不是 InMemorySaver：内存版在多 worker 下
    每个进程各存一份，同一个 thread_id 会时而记得时而失忆，重启也全丢。
    """
    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as saver:
        app.state.agent = build_agent(checkpointer=saver)
        yield


app = FastAPI(title="myAgent", lifespan=lifespan)

# 前端分离部署时要放开跨域，生产环境把 allow_origins 收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

"""漫剧 Agent 编排层（FastAPI + LangGraph）。

接口：
- POST /v1/dramas/{id}/run     启动（或崩溃后重放）剧集生成 DAG
- POST /v1/dramas/{id}/approve 人审结果 resume（approved=false 时图走向 END）
- GET  /v1/dramas/{id}/status  从 checkpoint 读取当前阶段
- GET  /health
"""
import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from . import config, graph, java_client

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("manju.main")

# 产物静态服务：/media/**（占位成片与预览视频；docker 中挂卷到 gateway 可直接访问）
os.makedirs(config.MEDIA_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.path.dirname(config.CHECKPOINT_DB) or ".", exist_ok=True)
    # AsyncSqliteSaver：checkpoint 持久化，进程重启后可断点续作
    saver_cm = AsyncSqliteSaver.from_conn_string(config.CHECKPOINT_DB)
    saver = await saver_cm.__aenter__()
    app.state.saver_cm = saver_cm
    app.state.graph = graph.build_graph(saver)
    yield
    await saver_cm.__aexit__(None, None, None)
    await java_client.close_client()


app = FastAPI(title="manju-agent", version="1.1.0", lifespan=lifespan)
app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")


class RunRequest(BaseModel):
    dramaId: str
    title: str = ""
    topic: str = ""
    traceId: str = ""


class ApproveRequest(BaseModel):
    approved: bool
    editedScript: str | None = None


async def _run_drama(drama_id: str, title: str, topic: str, trace_id: str) -> None:
    """后台执行 DAG；interrupt（人审暂停）与正常结束都视为一次完整的 invoke 返回。"""
    cfg = graph.thread_config(drama_id)
    try:
        logger.info("[%s] drama %s run start (title=%s)", trace_id or "-", drama_id, title)
        await app.state.graph.ainvoke(
            {"drama_id": drama_id, "title": title, "topic": topic, "trace_id": trace_id}, cfg)
        logger.info("[%s] drama %s invoke returned (paused or finished)", trace_id or "-", drama_id)
    except Exception as e:  # noqa: BLE001
        logger.error("[%s] drama %s failed: %s", trace_id or "-", drama_id, e)
        await java_client.report_event(drama_id, "failed", f"编排层异常：{e}")


@app.post("/v1/dramas/{drama_id}/run")
async def run(drama_id: str, req: RunRequest):
    # 幂等保护：已有未完结 thread 时拒绝重复启动（崩溃恢复由重放本接口或 approve 触发）
    cfg = graph.thread_config(drama_id)
    snap = await app.state.graph.aget_state(cfg)
    if snap is not None and snap.next:
        raise HTTPException(status_code=409, detail="drama already running or paused, use /approve to resume")
    asyncio.create_task(_run_drama(drama_id, req.title, req.topic, req.traceId))
    return {"ok": True, "dramaId": drama_id, "traceId": req.traceId, "status": "SUBMITTED"}


@app.post("/v1/dramas/{drama_id}/approve")
async def approve(drama_id: str, req: ApproveRequest):
    cfg = graph.thread_config(drama_id)
    snap = await app.state.graph.aget_state(cfg)
    if snap is None:
        raise HTTPException(status_code=404, detail="drama thread not found")
    if not snap.next:
        raise HTTPException(status_code=409, detail="drama already finished")
    asyncio.create_task(_resume_drama(drama_id, req.approved))
    return {"ok": True, "dramaId": drama_id, "status": "RESUMING"}


async def _resume_drama(drama_id: str, approved: bool) -> None:
    cfg = graph.thread_config(drama_id)
    try:
        await app.state.graph.ainvoke(Command(resume={"approved": approved}), cfg)
        logger.info("drama %s resumed, approved=%s (finished or next pause)", drama_id, approved)
    except Exception as e:  # noqa: BLE001
        logger.error("drama %s resume failed: %s", drama_id, e)
        await java_client.report_event(drama_id, "failed", f"恢复执行异常：{e}")


@app.get("/v1/dramas/{drama_id}/status")
async def status(drama_id: str):
    cfg = graph.thread_config(drama_id)
    snap = await app.state.graph.aget_state(cfg)
    if snap is None:
        raise HTTPException(status_code=404, detail="drama thread not found")
    values = snap.values or {}
    return {
        "dramaId": drama_id,
        "next": list(snap.next) if snap.next else [],
        "paused": bool(snap.next),
        "stage": _derive_stage(values, snap.next),
        "assetsReady": "assets" in values,
        "scriptReady": "script" in values,
        "approved": values.get("approved"),
        "shots": len(values.get("shots", [])),
        "videosDone": len(values.get("videos", [])),
        "voicesDone": len(values.get("voices", [])),
        "outputUrl": values.get("output_url", ""),
    }


def _derive_stage(values: dict, next_nodes) -> str:
    if values.get("output_url"):
        return "COMPLETED"
    if values.get("videos") or values.get("voices"):
        return "GENERATING_SUBTASKS"
    if values.get("shots"):
        return "SUBTASKS_DISPATCHED"
    if "approved" in values:
        return "REVIEWED"
    if values.get("script"):
        return "AWAIT_REVIEW" if next_nodes else "REVIEW_REJECTED"
    if values.get("assets"):
        return "SCRIPT_GENERATING"
    return "STARTING"


@app.get("/health")
async def health():
    from . import llm as llm_mod
    return {"ok": True, "service": "manju-agent", "dag": "built", "version": "1.3.0",
            "llm": "real" if llm_mod.is_configured() else "mock-fallback",
            "llmStats": llm_mod.stats()}


@app.get("/v1/llm/stats")
async def llm_stats():
    """token 用量与预算状态（运维监控用；生产版入 Prometheus）。"""
    from . import llm as llm_mod
    return llm_mod.stats()

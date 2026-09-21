"""对 Java 微服务的 HTTP 调用封装 + 向 orchestrator 上报阶段事件。

MVP：直接 REST + fire-and-forget 事件上报。
生产版演进：任务投递走 RocketMQ，事件走消息总线，本模块换成 MQ producer 即可，
DAG 节点代码不变（依赖倒置在 graph.py 层通过本模块隔离）。
"""
import logging

import httpx

from . import config

logger = logging.getLogger("manju.java_client")

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15.0)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


async def post_json(url: str, payload: dict) -> dict:
    resp = await get_client().post(url, json=payload)
    resp.raise_for_status()
    return resp.json()


async def get_json(url: str) -> dict:
    resp = await get_client().get(url)
    resp.raise_for_status()
    return resp.json()


async def report_event(drama_id: str, stage: str, message: str = "",
                       subtasks: list[dict] | None = None, **extra) -> None:
    """向 orchestrator 上报阶段事件（best-effort，失败不阻断 DAG）。"""
    body: dict = {"stage": stage, "message": message}
    if subtasks:
        body["subtasks"] = subtasks
    body.update(extra)
    url = f"{config.ORCHESTRATOR_URL}/api/dramas/{drama_id}/events"
    try:
        await post_json(url, body)
    except Exception as e:  # noqa: BLE001
        logger.warning("report_event failed (%s): %s", stage, e)

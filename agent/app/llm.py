"""LLM 接入层：OpenAI 兼容 Chat Completions + 结构化 JSON 输出。

配置（环境变量）：
    LLM_BASE_URL  如 https://api.deepseek.com/v1（OpenAI 兼容端点）
    LLM_API_KEY   密钥（绝不入库，走 .env / 部署平台密钥管理）
    LLM_MODEL     如 deepseek-chat / qwen-plus / gpt-4o-mini

未配置时 is_configured()=False，调用方回落 Mock（adapters 层保证两套并存）。
"""
import json
import logging
import os
import re

import httpx

logger = logging.getLogger("manju.llm")

MAX_JSON_RETRIES = 3


def is_configured() -> bool:
    return bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL"))


def _extract_json(text: str):
    """从模型输出中提取 JSON：容忍 ```json 围栏与前后闲话。"""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    # 剥离尾部多余逗号（LLM 常见笔误）
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


async def chat_json(system: str, user: str, llm_client: httpx.AsyncClient | None = None) -> dict:
    """调用 LLM 并解析为 JSON；解析失败带错误反馈重试 MAX_JSON_RETRIES 次。"""
    if not is_configured():
        raise RuntimeError("LLM not configured")

    base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
    model = os.getenv("LLM_MODEL", "deepseek-chat")
    headers = {"Authorization": f"Bearer {os.getenv('LLM_API_KEY', '')}"}

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    client = llm_client or httpx.AsyncClient(timeout=120.0)
    close_after = llm_client is None
    last_err = None
    try:
        for attempt in range(1, MAX_JSON_RETRIES + 1):
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages,
                      "temperature": 0.7, "response_format": {"type": "json_object"}},
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            try:
                return _extract_json(content)
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning("JSON parse failed (attempt %d): %s", attempt, e)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user",
                                 "content": f"输出不是合法 JSON（错误：{e}）。请只输出符合要求的 JSON，不要任何解释文字。"})
    finally:
        if close_after:
            await client.aclose()
    raise ValueError(f"LLM JSON output invalid after {MAX_JSON_RETRIES} retries: {last_err}")

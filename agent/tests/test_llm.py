"""LLM 接入层单测：stub OpenAI 兼容服务验证真实路径 + 无配置回落路径。

不依赖网络与真实密钥。
"""
import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import adapters, llm

LLM_PORT = 8901
CALLS = []


class FakeOpenAI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        CALLS.append(body)
        # 第1次返回非法 JSON（截断），验证 LLM 层带错误反馈重试；之后返回合法
        if len(CALLS) == 1:
            content = "剧本如下：\n```json\n{\"title\": \"测试剧\", \"scenes\": [{\"sceneId\": \"sc-001\", \"loc"
        else:
            content = json.dumps({
                "title": "测试剧", "characters": ["阿宝", "老王"],
                "scenes": [
                    {"sceneId": "sc-001", "location": "屋顶",
                     "description": "黄昏屋顶，少年望向城市",
                     "dialogues": [{"character": "阿宝", "emotion": "期待", "text": "总有一天我会飞过去。"}]},
                    {"sceneId": "sc-002", "location": "小巷",
                     "description": "雨夜小巷，路灯下两个身影对峙",
                     "dialogues": [{"character": "老王", "emotion": "低沉", "text": "路还长着呢。"}]},
                ]},
                ensure_ascii=False)
        resp = json.dumps({"choices": [{"message": {"content": content}}],
                           "usage": {"prompt_tokens": 100, "completion_tokens": 50}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


async def main():
    # ---------- 路径1：未配置 → 回落 Mock（调 Java script-svc stub 或直接断言） ----------
    for k in ("LLM_API_KEY", "LLM_BASE_URL"):
        os.environ.pop(k, None)
    assert not llm.is_configured()
    # 回落路径会调 script-svc:8083，起一个最小 stub
    from tests.stub_server import start_stubs
    start_stubs((8083,))
    script = await adapters.llm_generate_script("t1", "测试", "都市奇幻")
    assert script.get("totalScenes") == 3 and "scenes" in script  # mock 返回 3 场
    print("[1] 未配置 LLM → 回落 Mock OK")

    # ---------- 路径2：配置 → 真实调用（stub OpenAI） ----------
    os.environ["LLM_BASE_URL"] = f"http://127.0.0.1:{LLM_PORT}/v1"
    os.environ["LLM_API_KEY"] = "test-key"
    os.environ["LLM_MODEL"] = "test-model"
    assert llm.is_configured()

    srv = ThreadingHTTPServer(("127.0.0.1", LLM_PORT), FakeOpenAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    script = await adapters.llm_generate_script("t2", "屋顶上的少年", "成长")
    assert len(CALLS) == 2, f"expected retry once (2 calls), got {len(CALLS)}"
    assert script["totalScenes"] == 2 and script["scenes"][0]["sceneId"] == "sc-001"
    assert script["dramaId"] == "t2"
    # 重试时带上了错误反馈
    assert CALLS[1]["messages"][-1]["role"] == "user" and "合法 JSON" in CALLS[1]["messages"][-1]["content"]
    print("[2] 配置 LLM → 真实路径 OK：非法JSON自动重试1次后成功，结构校验通过")

    # ---------- 路径3：JSON 提取容错（围栏/尾逗号/前后闲话） ----------
    assert llm._extract_json('前言```json\n{"a": [1,2,],}\n```后记') == {"a": [1, 2]}
    print("[3] JSON 提取容错 OK：围栏+尾逗号+前后闲话")

    # ---------- 路径4：token 用量统计与预算限流 ----------
    s = llm.stats()
    assert s["calls"] == 2 and s["prompt_tokens"] == 200 and s["completion_tokens"] == 100, s
    assert s["total_tokens"] == 300 and s["budget"] == 0 and not s["budget_exceeded"]
    print("[4] token 用量统计 OK：2 次调用 / 300 tokens")

    # 设小预算触发限流 → chat_json 抛错 → adapters 回落 Mock
    os.environ["LLM_TOKEN_BUDGET"] = "300"
    script = await adapters.llm_generate_script("t3", "预算测试", "测试")  # 已超预算 → 回落 mock
    assert script.get("totalScenes") == 3  # mock 3 场
    assert llm.stats()["budget_exceeded"]
    del os.environ["LLM_TOKEN_BUDGET"]
    print("[5] 预算限流 OK：超预算自动回落 Mock，服务不中断")

    srv.shutdown()
    print("\nLLM ADAPTER TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

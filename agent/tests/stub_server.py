"""冒烟测试 stub：用 Python http.server 模拟 Java 微服务全部依赖接口。

模拟端口与真实服务一致：
  8081 orchestrator  POST /api/dramas/{id}/events
  8083 script-svc     POST /api/scripts/generate
  8084 asset-svc      POST /api/assets/prepare
  8085 storyboard-svc POST /api/storyboards/generate, POST /api/shots/video, GET /api/shots/video/{id}
  8086 voice-svc      POST /api/voices/generate
  8087 compose-svc    POST /api/compose

仅用于本机冒烟验证编排层 DAG（interrupt/resume/Send/checkpoint），不依赖 Java 运行时。
"""
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 记录 orchestrator 收到的事件，供测试断言
received_events: list[dict] = []
# video taskId -> submitted_at
_video_tasks: dict[str, float] = {}
_lock = threading.Lock()

SCRIPT = {
    "title": "", "characters": ["店主老周", "神秘顾客"], "totalScenes": 3,
    "scenes": [
        {"sceneId": "sc-001", "location": "深夜便利店",
         "description": "雨夜，城市角落的便利店亮着孤灯",
         "dialogues": [
             {"character": "店主老周", "emotion": "慵懒", "text": "又是没人的一晚上……"},
             {"character": "神秘顾客", "emotion": "低沉", "text": "一把伞，能修的那种。"}]},
        {"sceneId": "sc-002", "location": "便利店仓库",
         "description": "仓库深处透出微光",
         "dialogues": [
             {"character": "店主老周", "emotion": "惊讶", "text": "这些旧东西……在发光？"},
             {"character": "神秘顾客", "emotion": "平静", "text": "每件被修好的东西，都记得自己的故事。"}]},
        {"sceneId": "sc-003", "location": "便利店门口",
         "description": "雨停了，晨光初现",
         "dialogues": [
             {"character": "店主老周", "emotion": "释然", "text": "原来我修的不是伞，是人心啊。"}]},
    ],
}


def _shots_from_script():
    shots = []
    no = 1
    for sc in SCRIPT["scenes"]:
        for _ in range(2):
            shots.append({"shotNo": no, "sceneId": sc["sceneId"], "location": sc["location"],
                          "shotType": "中景", "cameraMove": "缓慢推近", "durationSec": 4 + no % 3,
                          "prompt": f"漫画风格，{sc['description']}"})
            no += 1
    return shots


class StubHandler(BaseHTTPRequestHandler):
    port = None  # 由 factory 注入

    def log_message(self, *args):  # 静音默认日志
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        p = self.path
        port = self.port

        if port == 8081:  # orchestrator events
            received_events.append({"path": p, "body": req})
            self._json({"ok": True})
        elif port == 8083:  # script-svc
            script = dict(SCRIPT)
            script["dramaId"] = req.get("dramaId", "")
            script["title"] = req.get("title", "")
            script["topic"] = req.get("topic", "")
            self._json(script)
        elif port == 8084:  # asset-svc
            self._json({"dramaId": req.get("dramaId", ""),
                        "characters": [{"name": "店主老周", "assetPackId": "pack-1",
                                        "refImages": ["/oss/mock/a.png"], "desc": "", "loraModelId": ""},
                                       {"name": "神秘顾客", "assetPackId": "pack-2",
                                        "refImages": ["/oss/mock/b.png"], "desc": "", "loraModelId": ""}],
                        "scenes": [{"name": "深夜便利店", "refImage": "/oss/mock/s1.png"}],
                        "voiceBindings": {"店主老周": "v1", "神秘顾客": "v2"}})
        elif port == 8085:
            if p == "/api/storyboards/generate":
                self._json({"dramaId": req.get("dramaId", ""), "shots": _shots_from_script(),
                            "totalShots": 6})
            elif p == "/api/shots/video":
                tid = "vt-" + uuid.uuid4().hex[:12]
                with _lock:
                    _video_tasks[tid] = time.time()
                self._json({"taskId": tid, "status": "SUBMITTED"})
            else:
                self._json({"error": "not found"}, 404)
        elif port == 8086:  # voice-svc
            text = req.get("text", "")
            self._json({"voiceId": "vo-" + uuid.uuid4().hex[:10], "sceneId": req.get("sceneId", ""),
                        "character": req.get("character", ""), "emotion": req.get("emotion", ""),
                        "audioUrl": "/oss/mock/v.mp3", "durationSec": round(len(text) * 0.25, 1),
                        "subtitle": text})
        elif port == 8087:  # compose-svc
            self._json({"dramaId": req.get("dramaId", ""),
                        "outputUrl": f"/oss/mock/drama_{req.get('dramaId', 'x')}_final_9x16.mp4",
                        "durationSec": 24.0, "resolution": "1080x1920",
                        "shotCount": len(req.get("shots", []))})
        else:
            self._json({"error": "no route"}, 404)

    def do_GET(self):
        p = self.path
        if self.port == 8085 and p.startswith("/api/shots/video/"):
            tid = p.rsplit("/", 1)[1]
            with _lock:
                submitted = _video_tasks.get(tid)
            if submitted is None:
                self._json({"taskId": tid, "status": "NOT_FOUND"})
            elif time.time() - submitted < 1.5:
                self._json({"taskId": tid, "status": "PROCESSING"})
            else:
                self._json({"taskId": tid, "status": "SUCCESS",
                            "videoUrl": f"/oss/mock/shot_{tid}.mp4", "resolution": "720p"})
        else:
            self._json({"error": "no route"}, 404)


def start_stubs(ports=(8081, 8083, 8084, 8085, 8086, 8087)):
    servers = []
    for port in ports:
        handler = type(f"Stub{port}", (StubHandler,), {"port": port})
        srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
    return servers

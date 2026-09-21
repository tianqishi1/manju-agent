"""环境配置：服务地址全部走环境变量，docker-compose / 本地运行均可覆盖。"""
import os


def _svc_url(env_key: str, default: str) -> str:
    return os.getenv(env_key, default)


ORCHESTRATOR_URL = _svc_url("ORCHESTRATOR_URL", "http://localhost:8081")
ASSET_SVC_URL = _svc_url("ASSET_SVC_URL", "http://localhost:8084")
SCRIPT_SVC_URL = _svc_url("SCRIPT_SVC_URL", "http://localhost:8083")
STORYBOARD_SVC_URL = _svc_url("STORYBOARD_SVC_URL", "http://localhost:8085")
VOICE_SVC_URL = _svc_url("VOICE_SVC_URL", "http://localhost:8086")
COMPOSE_SVC_URL = _svc_url("COMPOSE_SVC_URL", "http://localhost:8087")

AGENT_PORT = int(os.getenv("AGENT_PORT", "8000"))
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", "./data/checkpoints.db")
MEDIA_DIR = os.getenv("MEDIA_DIR", "./media")

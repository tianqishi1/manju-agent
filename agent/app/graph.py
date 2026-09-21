"""剧集生成 DAG（LangGraph）。

结构：
    START → prepare_assets → generate_script → review_gate(interrupt 剧本人审)
          → build_storyboard → preview_first_shot(首镜头预览视频) → style_gate(interrupt 画风审核)
          → [Send: render_shot × N（失败指数退避重试×2） ‖ synth_voice × M] → compose_drama(真实 mp4 渲染) → END

关键机制：
- interrupt()        两个人审点：剧本审核 + 首镜头画风审核，均 checkpoint 落盘等恢复
- Send API           镜头/配音 map-reduce 并行，videos/voices 用 operator.add reducer 合并
- SqliteSaver        checkpoint 持久化：进程崩溃重启后断点续作
- 指数退避重试       镜头视频失败重试 2 次（事件记录轨迹）后才降级
"""
import asyncio
import logging

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from . import adapters, java_client, render
from .state import DramaState

logger = logging.getLogger("manju.graph")

MAX_SHOT_RETRIES = 2  # 首次失败后额外重试次数


# ---------------- nodes ----------------

async def prepare_assets(state: DramaState) -> dict:
    drama_id = state["drama_id"]
    assets = await adapters.prepare_assets(drama_id, state.get("title", ""))
    chars = [c["name"] for c in assets.get("characters", [])]
    await java_client.report_event(drama_id, "assets_ready",
                                   f"素材准备完成：{len(chars)} 个角色资产包，{len(assets.get('scenes', []))} 个场景")
    return {"assets": assets}


async def generate_script(state: DramaState) -> dict:
    drama_id = state["drama_id"]
    script = await adapters.llm_generate_script(
        drama_id, state.get("title", ""), state.get("topic", ""))
    await java_client.report_event(
        drama_id, "script_generated",
        f"剧本生成完成：{script.get('totalScenes', 0)} 场，等待人审",
        script=script)
    return {"script": script}


async def review_gate(state: DramaState) -> dict:
    """剧本人审：interrupt() 暂停图执行，恢复值即审批结果。"""
    decision = interrupt({"prompt": "剧本待审核", "script": state.get("script", {})})
    approved = bool(decision.get("approved", False)) if isinstance(decision, dict) else bool(decision)
    if not approved:
        await java_client.report_event(state["drama_id"], "review_rejected", "人审拒绝，剧集终止")
    return {"approved": approved}


def route_after_review(state: DramaState):
    return "build_storyboard" if state.get("approved") else END


async def build_storyboard(state: DramaState) -> dict:
    drama_id = state["drama_id"]
    result = await adapters.build_storyboard(drama_id, state["script"])
    shots = result.get("shots", [])
    await java_client.report_event(drama_id, "storyboard_ready",
                                   f"分镜脚本完成：{len(shots)} 个镜头，渲染首镜头预览中")
    return {"shots": shots}


async def preview_first_shot(state: DramaState) -> dict:
    """渲染首镜头预览视频（画风审核素材）：一个镜头的占位 mp4。"""
    drama_id = state["drama_id"]
    shots = state.get("shots", [])
    first = shots[0] if shots else {}
    preview_url = await render.render_preview(drama_id, state.get("title", ""), first, state["script"])
    await java_client.report_event(
        drama_id, "style_review_pending",
        f"首镜头画风预览已生成（镜头1/{len(shots)}），请审核画风与角色形象",
        previewUrl=preview_url)
    return {"preview_url": preview_url}


async def style_gate(state: DramaState) -> dict:
    """画风人审：分镜图/首镜头视频一起看，一个镜头通过即可代表整体画风。"""
    decision = interrupt({"prompt": "画风审核", "preview_url": state.get("preview_url", ""),
                          "shot": state.get("shots", [{}])[0] if state.get("shots") else {}})
    approved = bool(decision.get("approved", False)) if isinstance(decision, dict) else bool(decision)
    if not approved:
        await java_client.report_event(state["drama_id"], "style_review_rejected",
                                       "画风审核未通过，剧集终止（生产版：可带意见回到分镜重生成）")
    return {"approved": approved}


def route_after_style(state: DramaState):
    return fan_out(state) if state.get("approved") else END


def fan_out(state: DramaState) -> list[Send]:
    """Send API 并行展开：每个镜头一个视频生成分支 + 每条对白一个配音分支。"""
    drama_id = state["drama_id"]
    sends: list[Send] = [
        Send("render_shot", {"drama_id": drama_id, "shot": shot})
        for shot in state.get("shots", [])
    ]
    for scene in state["script"].get("scenes", []):
        for dialogue in scene.get("dialogues", []):
            sends.append(Send("synth_voice", {"drama_id": drama_id, "scene": scene, "dialogue": dialogue}))
    return sends


async def render_shot(payload: dict) -> dict:
    """单镜头视频生成（Send 分支）：失败指数退避重试 MAX_SHOT_RETRIES 次后降级。"""
    drama_id = payload["drama_id"]
    shot = payload["shot"]
    shot_no = shot["shotNo"]
    last_err = None
    for attempt in range(1 + MAX_SHOT_RETRIES):
        try:
            video = await adapters.generate_shot_video(drama_id, shot)
            await java_client.report_event(
                drama_id, "shot_done",
                f"镜头 {shot_no} 视频生成完成" + (f"（第 {attempt + 1} 次尝试成功）" if attempt else ""),
                subtasks=[{"type": "SHOT_VIDEO", "refId": str(shot_no),
                           "status": "SUCCESS", "artifactUrl": video["videoUrl"]}])
            return {"videos": [video]}
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < MAX_SHOT_RETRIES:
                await java_client.report_event(
                    drama_id, "shot_retry",
                    f"镜头 {shot_no} 第 {attempt + 1} 次失败：{e}，{2 ** attempt}s 后重试")
                await asyncio.sleep(2 ** attempt)
    logger.error("shot %s failed after %d retries: %s", shot_no, MAX_SHOT_RETRIES, last_err)
    await java_client.report_event(
        drama_id, "shot_failed",
        f"镜头 {shot_no} 重试 {MAX_SHOT_RETRIES} 次后仍失败（生产版：换供应商→静态图+动效降级）",
        subtasks=[{"type": "SHOT_VIDEO", "refId": str(shot_no), "status": "FAILED"}])
    return {"videos": []}


async def synth_voice(payload: dict) -> dict:
    """单条对白配音（Send 分支）。"""
    drama_id = payload["drama_id"]
    voice = await adapters.generate_voice(drama_id, payload["scene"], payload["dialogue"])
    await java_client.report_event(
        drama_id, "voice_done",
        f"配音完成：[{voice['character']}] {voice['subtitle'][:20]}… ({voice['durationSec']}s)",
        subtasks=[{"type": "VOICE", "refId": str(voice["voiceId"]),
                   "status": "SUCCESS", "artifactUrl": voice["audioUrl"]}])
    return {"voices": [voice]}


async def compose_drama(state: DramaState) -> dict:
    """成片：先调 compose-svc（Java 合成域，返回时长/规格元数据），再渲染真实可播放 mp4。"""
    drama_id = state["drama_id"]
    videos = state.get("videos", [])
    voices = state.get("voices", [])
    await java_client.report_event(drama_id, "composing",
                                   f"全部子任务汇齐（{len(videos)} 视频 / {len(voices)} 配音），开始合成")
    meta = await adapters.compose_drama(drama_id, state.get("shots", []), videos, voices)
    output_url = await render.render_final(
        drama_id, state.get("title", ""), state.get("shots", []), state["script"])
    await java_client.report_event(
        drama_id, "completed",
        f"成片完成：{meta.get('durationSec', 0)}s / {meta.get('resolution', '')} → {output_url}",
        outputUrl=output_url,
        subtasks=[{"type": "COMPOSE", "refId": drama_id,
                   "status": "SUCCESS", "artifactUrl": output_url}])
    return {"output_url": output_url}


# ---------------- graph build ----------------

def build_graph(checkpointer):
    g = StateGraph(DramaState)

    g.add_node("prepare_assets", prepare_assets)
    g.add_node("generate_script", generate_script)
    g.add_node("review_gate", review_gate)
    g.add_node("build_storyboard", build_storyboard)
    g.add_node("preview_first_shot", preview_first_shot)
    g.add_node("style_gate", style_gate)
    g.add_node("render_shot", render_shot)
    g.add_node("synth_voice", synth_voice)
    g.add_node("compose_drama", compose_drama)

    g.add_edge(START, "prepare_assets")
    g.add_edge("prepare_assets", "generate_script")
    g.add_edge("generate_script", "review_gate")
    g.add_conditional_edges("review_gate", route_after_review,
                            {"build_storyboard": "build_storyboard", END: END})
    g.add_edge("build_storyboard", "preview_first_shot")
    g.add_edge("preview_first_shot", "style_gate")
    g.add_conditional_edges("style_gate", route_after_style,
                            ["render_shot", "synth_voice", END])
    g.add_edge("render_shot", "compose_drama")
    g.add_edge("synth_voice", "compose_drama")
    g.add_edge("compose_drama", END)

    return g.compile(checkpointer=checkpointer)


def thread_config(drama_id: str) -> dict:
    """每部剧一个 thread：checkpoint 恢复、人审 resume 都以此为键。"""
    return {"configurable": {"thread_id": f"drama-{drama_id}"}}


__all__ = ["build_graph", "thread_config", "AsyncSqliteSaver"]

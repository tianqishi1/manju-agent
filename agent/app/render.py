"""分镜卡片渲染 + mp4 合成（PyAV + Pillow）。

MVP 阶段生成「可播放占位成片」：每镜头渲染为分镜卡片（画面描述/台词/字幕/镜头信息），
按镜头时长拼接为 9:16 mp4，写入 MEDIA_DIR，经 FastAPI StaticFiles 以 /media/** 提供。
生产版替换为：真实分镜视频片段 + 音轨对齐 + FFmpeg Worker 池 + 云剪辑降级（技术方案 §4.6）。
"""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import av
from PIL import Image, ImageDraw, ImageFont

from . import config

W, H = 720, 1280
FPS = 10
BG = (16, 18, 26)
FG = (230, 232, 238)
MUTED = (138, 144, 160)
ACCENT = (76, 110, 245)

_FONT_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "assets", "fonts", "msyh.ttc"),
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_executor = ThreadPoolExecutor(max_workers=2)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in _FONT_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines, line = [], ""
    for ch in text:
        if draw.textlength(line + ch, font=font) <= max_width:
            line += ch
        else:
            lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines


def _draw_card(title: str, shot: dict, scene: dict | None) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_title, f_body, f_dlg, f_tag = _font(30), _font(34), _font(30), _font(24)

    # 顶部：剧集标题
    d.text((40, 48), title[:16], font=f_title, fill=MUTED)
    d.line([(40, 100), (W - 40, 100)], fill=(50, 56, 72), width=2)

    # 镜头信息角标
    tag = f"镜头 {shot.get('shotNo', '?')} · {shot.get('shotType', '')} · {shot.get('cameraMove', '')} · {shot.get('durationSec', 4)}s"
    d.rounded_rectangle((40, 120, 40 + d.textlength(tag, font=f_tag) + 28, 170), 12, fill=(38, 44, 60))
    d.text((54, 130), tag, font=f_tag, fill=FG)

    # 中部：画面描述
    desc = str(scene.get("description", shot.get("prompt", ""))) if scene else str(shot.get("prompt", ""))
    y = 240
    for line in _wrap(d, desc, f_body, W - 80)[:8]:
        d.text((40, y), line, font=f_body, fill=FG)
        y += 50

    # 对白（角色名 + 台词）
    if scene:
        y = max(y + 60, 620)
        for dlg in scene.get("dialogues", [])[:4]:
            speaker = f"{dlg.get('character', '')}（{dlg.get('emotion', '')}）"
            d.text((40, y), speaker, font=f_tag, fill=ACCENT if False else (122, 162, 247))
            y += 34
            for line in _wrap(d, str(dlg.get("text", "")), f_dlg, W - 80)[:2]:
                d.text((56, y), line, font=f_dlg, fill=FG)
                y += 42
            y += 24

    # 底部：位置 + 占位说明
    d.line([(40, H - 120), (W - 40, H - 120)], fill=(50, 56, 72), width=2)
    loc = f"场景：{shot.get('location', '')}" if scene else ""
    d.text((40, H - 100), loc, font=f_tag, fill=MUTED)
    d.text((40, H - 64), "MVP 占位成片 · 接入真实模型后为分镜视频", font=f_tag, fill=MUTED)
    return img


def _encode(path: str, cards: list[tuple[Image.Image, float]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    container = av.open(path, mode="w")
    stream = container.add_stream("libx264", rate=FPS)
    stream.width, stream.height = W, H
    stream.pix_fmt = "yuv420p"
    for img, dur_sec in cards:
        frame_count = max(1, int(dur_sec * FPS))
        for i in range(frame_count):
            frame = av.VideoFrame.from_image(img)
            for packet in stream.encode(frame):
                container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _scene_of(script: dict, shot: dict) -> dict | None:
    for sc in script.get("scenes", []):
        if str(sc.get("sceneId")) == str(shot.get("sceneId")):
            return sc
    return None


async def render_preview(drama_id: str, title: str, shot: dict, script: dict) -> str:
    """首镜头画风预览（style_gate 审核素材）。"""
    url = await asyncio.get_running_loop().run_in_executor(
        _executor, _render_sync, drama_id, title, [shot], script, "preview")
    return url


async def render_final(drama_id: str, title: str, shots: list, script: dict) -> str:
    """完整占位成片：全部镜头卡片按时长拼接。"""
    url = await asyncio.get_running_loop().run_in_executor(
        _executor, _render_sync, drama_id, title, shots, script, "final_9x16")
    return url


def _render_sync(drama_id: str, title: str, shots: list, script: dict, name: str) -> str:
    cards = [(_draw_card(title, s, _scene_of(script, s)), float(s.get("durationSec", 4))) for s in shots]
    rel = f"drama_{drama_id}/{name}.mp4"
    path = os.path.join(config.MEDIA_DIR, rel)
    _encode(path, cards)
    return f"/media/{rel}"

"""编排层端到端冒烟测试（无需 Java 运行时）。

覆盖：
1. DAG 全流程：素材→剧本→interrupt 剧本人审暂停（checkpoint）
2. 剧本批准 resume → 首镜头预览渲染 → interrupt 画风审核暂停
3. 画风批准 resume → Send 并行分镜视频+配音 → 真实 mp4 渲染 → 完成
4. 剧本拒绝路径：直接 END，不触发分镜
5. checkpoint 持久化：同一 Sqlite DB 新建 graph 实例，thread 状态可恢复读取
6. orchestrator 事件流断言：双审核事件 / shot_done / completed 等
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.types import Command

from tests.stub_server import received_events, start_stubs


async def main():
    tmpdir = tempfile.mkdtemp(prefix="manju-smoke-")
    os.environ["CHECKPOINT_DB"] = os.path.join(tmpdir, "ckpt.db")
    os.environ["MEDIA_DIR"] = os.path.join(tmpdir, "media")
    for key, port in [("ORCHESTRATOR_URL", 8081), ("SCRIPT_SVC_URL", 8083),
                      ("ASSET_SVC_URL", 8084), ("STORYBOARD_SVC_URL", 8085),
                      ("VOICE_SVC_URL", 8086), ("COMPOSE_SVC_URL", 8087)]:
        os.environ[key] = f"http://127.0.0.1:{port}"

    start_stubs()

    from app import graph
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    async with AsyncSqliteSaver.from_conn_string(os.environ["CHECKPOINT_DB"]) as saver:
        g = graph.build_graph(saver)

        # ---------- 场景 1：剧本人审暂停 ----------
        cfg = graph.thread_config("smoke-001")
        await g.ainvoke({"drama_id": "smoke-001", "title": "深夜便利店的一千零一夜",
                         "topic": "都市奇幻"}, cfg)

        snap = await g.aget_state(cfg)
        assert snap.next == ("review_gate",), f"expected pause at review_gate, got {snap.next}"
        assert snap.values.get("script", {}).get("totalScenes") == 3, "script not generated"
        assert "assets" in snap.values, "assets not prepared"
        print("[1] 剧本人审 interrupt OK")

        # ---------- 场景 2：批准 → 画风审核暂停（含预览视频渲染） ----------
        await g.ainvoke(Command(resume={"approved": True}), cfg)
        snap = await g.aget_state(cfg)
        assert snap.next == ("style_gate",), f"expected pause at style_gate, got {snap.next}"
        preview = snap.values.get("preview_url", "")
        assert preview.startswith("/media/") and preview.endswith(".mp4"), f"preview_url bad: {preview}"
        preview_path = os.path.join(os.environ["MEDIA_DIR"], preview.replace("/media/", ""))
        assert os.path.exists(preview_path) and os.path.getsize(preview_path) > 1000, "preview mp4 not rendered"
        with open(preview_path, "rb") as f:
            assert f.read(8)[4:8] == b"ftyp", "preview is not a valid mp4"
        print(f"[2] 画风审核 interrupt OK：预览视频已真实渲染 {preview} ({os.path.getsize(preview_path)} bytes)")

        # ---------- 场景 3：画风批准 → 并行生成 → 真实成片 ----------
        await g.ainvoke(Command(resume={"approved": True}), cfg)
        snap = await g.aget_state(cfg)
        vals = snap.values
        assert not snap.next, f"graph not finished: {snap.next}"
        out = vals.get("output_url", "")
        assert out.startswith("/media/") and out.endswith(".mp4"), f"output_url bad: {out}"
        out_path = os.path.join(os.environ["MEDIA_DIR"], out.replace("/media/", ""))
        assert os.path.exists(out_path) and os.path.getsize(out_path) > 10000, "final mp4 not rendered"
        assert len(vals.get("videos", [])) == 6, f"videos={len(vals.get('videos', []))}, expect 6"
        assert len(vals.get("voices", [])) == 5, f"voices={len(vals.get('voices', []))}, expect 5"
        print(f"[3] Send 并行 + 真实成片 OK：6 视频 + 5 配音 → {out} ({os.path.getsize(out_path)} bytes)")

        ev_stages = [e["body"].get("stage") for e in received_events]
        assert ev_stages.count("shot_done") == 6 and ev_stages.count("voice_done") == 5
        assert "style_review_pending" in ev_stages and "composing" in ev_stages and "completed" in ev_stages
        print("[3] 事件流 OK：style_review_pending / 6×shot_done / 5×voice_done / completed")

        # ---------- 场景 4：剧本拒绝路径 ----------
        n_before = len(received_events)
        cfg2 = graph.thread_config("smoke-002")
        await g.ainvoke({"drama_id": "smoke-002", "title": "被拒绝的剧", "topic": "test"}, cfg2)
        await g.ainvoke(Command(resume={"approved": False}), cfg2)
        snap2 = await g.aget_state(cfg2)
        assert not snap2.next, "rejection path not finished"
        assert not snap2.values.get("videos"), "rejected drama should have no videos"
        assert not snap2.values.get("output_url"), "rejected drama should have no output"
        new_stages = [e["body"].get("stage") for e in received_events[n_before:]]
        assert "style_review_pending" not in new_stages and "completed" not in new_stages
        print("[4] 拒绝路径 OK：直接终止，无分镜/合成调用")

        # ---------- 场景 5：checkpoint 持久化（新 graph 实例读同一 DB） ----------
    async with AsyncSqliteSaver.from_conn_string(os.environ["CHECKPOINT_DB"]) as saver2:
        g2 = graph.build_graph(saver2)  # 模拟进程重启后重建
        snap3 = await g2.aget_state(graph.thread_config("smoke-001"))
        assert snap3.values.get("output_url", "").endswith(".mp4"), "checkpoint lost after rebuild"
        assert not snap3.next
        print("[5] checkpoint 持久化 OK：新实例从 Sqlite 恢复 thread 状态")

    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

"""剧集生成 DAG 的共享状态定义。

videos / voices 使用 operator.add reducer：Send 并行分支各自返回增量，
LangGraph 自动合并，支撑 map-reduce 模式的分镜并行生成。
"""
import operator
from typing import Annotated, Any, TypedDict


class DramaState(TypedDict, total=False):
    drama_id: str
    title: str
    topic: str

    # 素材准备产物（角色资产包 / 场景图 / 音色绑定）
    assets: dict[str, Any]

    # 结构化剧本（scenes / dialogues / characters）
    script: dict[str, Any]

    # 人审结果（interrupt resume 值）
    approved: bool

    # 首镜头画风预览（style_gate 审核素材）
    preview_url: str

    # 镜头脚本列表
    shots: list[dict[str, Any]]

    # 并行分支产物（reducer 合并）
    videos: Annotated[list[dict[str, Any]], operator.add]
    voices: Annotated[list[dict[str, Any]], operator.add]

    # 成片
    output_url: str

    error: str

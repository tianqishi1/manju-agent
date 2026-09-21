# 漫剧 Agent 平台 MVP（微服务骨架）

> 对应《漫剧Agent平台技术方案》一期 MVP 范围：单租户全链路（剧本→分镜→配音→合成）+
> LangGraph DAG 编排 + 剧本人审 + 断点续作。模型接入 Mock 先行，接口契约即真实模型契约。

## 架构

```
浏览器 ──→ gateway(8080, Spring Cloud Gateway + 静态前端)
              ├─→ orchestrator(8081, 剧集状态机/子任务表/事件/人审, H2)
              ├─→ topic-svc(8082, 选题)
              └─→ agent(8000, FastAPI + LangGraph DAG)
                      ├─→ asset-svc(8084, 素材/角色资产包)
                      ├─→ script-svc(8083, 剧本)
                      ├─→ storyboard-svc(8085, 分镜+视频任务, 提交-轮询模型)
                      ├─→ voice-svc(8086, TTS 配音)
                      └─→ compose-svc(8087, 成片合成)
```

**DAG（agent/app/graph.py）**：

```
START → prepare_assets → generate_script → review_gate(interrupt 人审)
      → build_storyboard → [Send: render_shot × N ‖ synth_voice × M] → compose_drama → END
```

- `interrupt()`：剧本生成后图暂停（checkpoint 落 Sqlite），前端审批后由 orchestrator 调 `/approve` 恢复
- `Send API`：每镜头一个视频分支 + 每条对白一个配音分支并行执行，`operator.add` reducer 合并
- `AsyncSqliteSaver`：进程重启后 `POST /run` 重放 / `POST /approve` 从最近 checkpoint 断点续作

## 运行（Docker，推荐）

要求：Docker + docker compose。本机未装 Docker 时见下方「无 Docker 运行」。

```bash
cd manju-agent
docker compose up --build
# 打开 http://localhost:8080
```

## 无 Docker 运行（本机开发）

要求：JDK 17+、Maven 3.8+（构建 Java 侧）；Python 3.10+（运行编排层）。

```bash
# 1. Java 侧（8 个服务分 8 个终端，或用脚本依次启动）
cd services
mvn -pl orchestrator -am package -DskipTests
java -jar orchestrator/target/*.jar
# 其余模块同理：gateway topic-svc script-svc asset-svc storyboard-svc voice-svc compose-svc

# 2. Python 编排层
cd ../agent
py -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# 3. 打开 http://localhost:8080
```

## 端到端流程

1. 页面选选题 → `POST /api/dramas` → orchestrator 建剧集（RUNNING）→ 异步调 agent `/run`
2. DAG 执行：素材 → 剧本 → **interrupt 暂停**，orchestrator 收到 `script_generated` 事件转 AWAIT_REVIEW
3. 页面展示剧本 JSON → 批准 → orchestrator 调 agent `/approve`（`Command(resume=...)`）
4. 分镜脚本 → Send 并行：N 个镜头视频 + M 条配音（storyboard-svc 的 Mock 视频 1.5s 完成模拟异步任务）
5. 汇齐 → compose-svc 合成 → `completed` 事件 → 状态 COMPLETED，输出成片 URL

## Mock → 生产 替换点

| Mock 位置 | 生产替换 |
|-----------|---------|
| script-svc `/generate` | 模型路由网关 LLM 适配器（OpenAI 兼容），JSON Schema 校验 + 重试 |
| storyboard-svc `/shots/video` | 模型路由网关视频适配器（可灵/Seedance/万相 API 池 + 自部署 Wan2.2），提交-轮询换回调驱动 |
| voice-svc `/generate` | TTS 适配器（火山/Azure + GPT-SoVITS/CosyVoice） |
| compose-svc | FFmpeg Worker 池（K8s Job）+ 云剪辑降级 |
| orchestrator H2 + REST 直调 | MySQL 分库分表 + RocketMQ 事务消息 + Nacos + Sentinel |
| agent 节点内轮询 | interrupt + 网关回调 resume（技术方案 §4.4） |

## 目录

```
manju-agent/
├── docker-compose.yml
├── services/               # Maven 多模块（父 pom）
│   ├── gateway/            # 8080 网关 + 静态前端
│   ├── orchestrator/       # 8081 剧集总控（状态机/事件/子任务表/审批）
│   ├── topic-svc/          # 8082 选题
│   ├── script-svc/         # 8083 剧本
│   ├── asset-svc/          # 8084 素材
│   ├── storyboard-svc/     # 8085 分镜 + 视频任务（提交-轮询）
│   ├── voice-svc/          # 8086 配音
│   └── compose-svc/        # 8087 合成
└── agent/                  # Python LangGraph 编排层
    └── app/{main,graph,state,adapters,java_client,config}.py
```

package com.manju.orchestrator;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 剧集总控（MVP 版）。
 * 职责：创建剧集 → 触发 Python LangGraph 编排 → 接收阶段事件推进状态机 → 人审批准/拒绝。
 * 生产版演进：RocketMQ 事务消息保证「建任务+投递」原子性；子任务表分库分表；租户配额校验。
 */
@RestController
@RequestMapping("/api/dramas")
public class DramaController {

    private static final Logger log = LoggerFactory.getLogger(DramaController.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final DramaRepository dramas;
    private final DramaEventRepository events;
    private final SubtaskRepository subtasks;
    private final AgentClient agent;

    public DramaController(DramaRepository dramas, DramaEventRepository events,
                           SubtaskRepository subtasks, AgentClient agent) {
        this.dramas = dramas;
        this.events = events;
        this.subtasks = subtasks;
        this.agent = agent;
    }

    @PostMapping
    @Transactional
    public Map<String, Object> create(@RequestBody Map<String, String> req) {
        Drama d = new Drama();
        d.setTitle(req.getOrDefault("title", "未命名漫剧"));
        d.setTopic(req.getOrDefault("topic", ""));
        d.setStatus(Drama.Status.RUNNING);
        d = dramas.save(d);
        addEvent(d.getId(), "drama_created", "剧集已创建，提交编排层执行");
        agent.runDramaAsync(d.getId(), d.getTitle(), d.getTopic());
        return Map.of("id", d.getId(), "status", d.getStatus().name());
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable Long id) {
        return dramas.findById(id).map(d -> ResponseEntity.ok(toDetail(d)))
                .orElse(ResponseEntity.notFound().build());
    }

    /** 编排层阶段事件回调：stage ∈ assets_ready/script_generated/review_approved/shot_done/voice_done/completed/failed */
    @PostMapping("/{id}/events")
    @Transactional
    public Map<String, Object> onEvent(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        Drama d = dramas.findById(id).orElse(null);
        if (d == null) return Map.of("ok", false, "error", "drama not found");

        String stage = String.valueOf(body.getOrDefault("stage", ""));
        String message = String.valueOf(body.getOrDefault("message", ""));
        addEvent(id, stage, message);

        switch (stage) {
            case "script_generated" -> {
                Object script = body.get("script");
                if (script != null) {
                    try { d.setScriptJson(MAPPER.writeValueAsString(script)); }
                    catch (Exception e) { log.warn("script serialize failed", e); }
                }
                d.setStatus(Drama.Status.AWAIT_REVIEW);
                d.setReviewKind("SCRIPT");
            }
            case "style_review_pending" -> {
                d.setStatus(Drama.Status.AWAIT_REVIEW);
                d.setReviewKind("STYLE");
                Object pv = body.get("previewUrl");
                if (pv != null) d.setPreviewUrl(String.valueOf(pv));
            }
            case "review_approved", "style_review_approved", "storyboard_ready" -> {
                d.setStatus(Drama.Status.RUNNING);
                d.setReviewKind(null);
            }
            case "review_rejected", "style_review_rejected" -> {
                d.setStatus(Drama.Status.REJECTED);
                d.setReviewKind(null);
            }
            case "completed" -> {
                d.setStatus(Drama.Status.COMPLETED);
                d.setOutputUrl(String.valueOf(body.getOrDefault("outputUrl", "")));
                d.setReviewKind(null);
            }
            case "failed" -> d.setStatus(Drama.Status.FAILED);
            default -> { /* 阶段性事件不改状态 */ }
        }
        d.setUpdatedAt(java.time.LocalDateTime.now());
        dramas.save(d);

        // 子任务 upsert（SHOT_VIDEO / VOICE / COMPOSE 粒度）
        Object stObj = body.get("subtasks");
        if (stObj instanceof List<?> list) {
            for (Object o : list) {
                if (o instanceof Map<?, ?> m) {
                    Object artObj = m.get("artifactUrl");
                    upsertSubtask(id,
                            String.valueOf(m.get("type")),
                            String.valueOf(m.get("refId")),
                            String.valueOf(m.get("status")),
                            artObj == null ? "" : String.valueOf(artObj));
                }
            }
        }
        return Map.of("ok", true);
    }

    /** 人审：批准 → resume LangGraph interrupt；拒绝 → 终止 */
    @PostMapping("/{id}/approve")
    @Transactional
    public Map<String, Object> approve(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        Drama d = dramas.findById(id).orElse(null);
        if (d == null) return Map.of("ok", false, "error", "drama not found");
        if (d.getStatus() != Drama.Status.AWAIT_REVIEW) {
            return Map.of("ok", false, "error", "status is " + d.getStatus());
        }
        boolean approved = Boolean.TRUE.equals(body.get("approved"));
        if (approved) {
            d.setStatus(Drama.Status.RUNNING);
            d.setReviewKind(null);
            dramas.save(d);
            String kind = "STYLE".equals(body.getOrDefault("_kind", "")) ? "画风" : "剧本";
            addEvent(id, "review_submitted", kind + "审核通过，恢复 DAG 执行");
            String edited = body.get("editedScript") == null ? null : String.valueOf(body.get("editedScript"));
            agent.approveDramaAsync(id, true, edited);
        } else {
            d.setStatus(Drama.Status.REJECTED);
            d.setReviewKind(null);
            dramas.save(d);
            addEvent(id, "review_rejected", "人审拒绝，剧集终止");
            agent.approveDramaAsync(id, false, null);
        }
        return Map.of("ok", true, "status", d.getStatus().name());
    }

    // ---------- helpers ----------

    private void addEvent(Long dramaId, String stage, String message) {
        DramaEvent e = new DramaEvent();
        e.setDramaId(dramaId);
        e.setStage(stage);
        e.setMessage(message);
        events.save(e);
    }

    private void upsertSubtask(Long dramaId, String type, String refId, String status, String artifactUrl) {
        Subtask st = subtasks.findByDramaIdAndTypeAndRefId(dramaId, type, refId).orElseGet(() -> {
            Subtask n = new Subtask();
            n.setDramaId(dramaId);
            n.setType(type);
            n.setRefId(refId);
            return n;
        });
        try { st.setStatus(Subtask.Status.valueOf(status)); } catch (Exception ignore) {}
        if (artifactUrl != null && !artifactUrl.isBlank() && !"null".equals(artifactUrl)) {
            st.setArtifactUrl(artifactUrl);
        }
        subtasks.save(st);
    }

    private Map<String, Object> toDetail(Drama d) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", d.getId());
        m.put("title", d.getTitle());
        m.put("topic", d.getTopic());
        m.put("status", d.getStatus().name());
        m.put("reviewKind", d.getReviewKind());
        m.put("previewUrl", d.getPreviewUrl());
        m.put("outputUrl", d.getOutputUrl());
        m.put("createdAt", String.valueOf(d.getCreatedAt()));
        if (d.getScriptJson() != null) {
            try { m.put("script", MAPPER.readValue(d.getScriptJson(), Object.class)); }
            catch (Exception ignore) { m.put("scriptRaw", d.getScriptJson()); }
        }
        List<Map<String, Object>> evs = new ArrayList<>();
        for (DramaEvent e : events.findByDramaIdOrderByIdAsc(d.getId())) {
            evs.add(Map.of("stage", e.getStage(),
                    "message", e.getMessage() == null ? "" : e.getMessage(),
                    "createdAt", String.valueOf(e.getCreatedAt())));
        }
        m.put("events", evs);
        List<Map<String, Object>> sts = new ArrayList<>();
        for (Subtask s : subtasks.findByDramaIdOrderByIdAsc(d.getId())) {
            sts.add(Map.of("type", s.getType(), "refId", s.getRefId(),
                    "status", s.getStatus().name(),
                    "artifactUrl", s.getArtifactUrl() == null ? "" : s.getArtifactUrl()));
        }
        m.put("subtasks", sts);
        return m;
    }
}

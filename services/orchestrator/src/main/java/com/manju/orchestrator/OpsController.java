package com.manju.orchestrator;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.*;

/**
 * 运维看板（MVP 版）：多剧集总览、卡死检测、失败子任务聚合。
 * 生产版演进：指标入 Prometheus（队列深度/子任务成功率/各供应商 P95），Grafana 大盘 + 告警。
 */
@RestController
@RequestMapping("/api/ops")
public class OpsController {

    private final DramaRepository dramas;
    private final DramaEventRepository events;
    private final SubtaskRepository subtasks;

    @Value("${ops.stuck-after-seconds:300}")
    private long stuckAfterSeconds;

    public OpsController(DramaRepository dramas, DramaEventRepository events, SubtaskRepository subtasks) {
        this.dramas = dramas;
        this.events = events;
        this.subtasks = subtasks;
    }

    /** 卡死判定：RUNNING 状态且超过阈值无更新（AWAIT_REVIEW 是合法等人，不算卡死） */
    List<Drama> findStuck(long thresholdSec) {
        LocalDateTime deadline = LocalDateTime.now().minusSeconds(thresholdSec);
        List<Drama> stuck = new ArrayList<>();
        for (Drama d : dramas.findAll()) {
            if (d.getStatus() == Drama.Status.RUNNING && d.getUpdatedAt().isBefore(deadline)) {
                stuck.add(d);
            }
        }
        return stuck;
    }

    @GetMapping("/board")
    public Map<String, Object> board(@RequestParam(required = false) Long stuckAfterSec) {
        long threshold = stuckAfterSec != null ? stuckAfterSec : stuckAfterSeconds;

        Map<String, Integer> statusCounts = new LinkedHashMap<>();
        for (Drama.Status s : Drama.Status.values()) statusCounts.put(s.name(), 0);
        List<Drama> all = dramas.findAll();
        for (Drama d : all) statusCounts.merge(d.getStatus().name(), 1, Integer::sum);

        List<Map<String, Object>> stuckList = findStuck(threshold).stream().<Map<String, Object>>map(d -> Map.of(
                "id", d.getId(), "title", d.getTitle(),
                "updatedAt", String.valueOf(d.getUpdatedAt()),
                "stuckSeconds", Duration.between(d.getUpdatedAt(), LocalDateTime.now()).getSeconds()
        )).toList();

        List<Map<String, Object>> failed = new ArrayList<>();
        for (Subtask s : subtasks.findByStatus(Subtask.Status.FAILED)) {
            failed.add(Map.of("dramaId", s.getDramaId(), "type", s.getType(),
                    "refId", s.getRefId(), "status", s.getStatus().name()));
        }

        List<Map<String, Object>> recent = new ArrayList<>();
        for (Drama d : dramas.findTop20ByOrderByIdDesc()) {
            List<DramaEvent> evs = events.findByDramaIdOrderByIdAsc(d.getId());
            String lastStage = evs.isEmpty() ? "" : evs.get(evs.size() - 1).getStage();
            Map<String, Object> m = new HashMap<>();
            m.put("id", d.getId());
            m.put("traceId", d.getTraceId());
            m.put("title", d.getTitle());
            m.put("status", d.getStatus().name());
            m.put("reviewKind", d.getReviewKind());
            m.put("lastStage", lastStage);
            m.put("updatedAt", String.valueOf(d.getUpdatedAt()));
            recent.add(m);
        }

        int total = all.size();
        int completed = statusCounts.get("COMPLETED");
        int failedDramas = statusCounts.get("FAILED") + statusCounts.get("REJECTED");
        return Map.of(
                "total", total,
                "successRate", total == 0 ? "n/a" : String.format("%.0f%%", completed * 100.0 / total),
                "statusCounts", statusCounts,
                "stuckThresholdSeconds", threshold,
                "stuck", stuckList,
                "failedSubtasks", failed,
                "recent", recent);
    }
}

package com.manju.storyboard;

import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 分镜域（MVP Mock 版）。
 * 生产版：① 剧本→镜头脚本（LLM 辅助镜头语言切分）② 分镜图生成（图生图+角色资产包）
 * ③ 图生视频：统一走「模型路由网关」（可灵/Seedance/万相 商业API池 + 自部署 Wan2.2 兜底），
 * 本 Mock 模拟「提交任务 → 轮询 → 约1.5s后成功」的异步任务模型。
 */
@RestController
@RequestMapping("/api")
public class StoryboardController {

    /** taskId -> submittedAtMillis */
    private final Map<String, Long> videoTasks = new ConcurrentHashMap<>();

    @PostMapping("/storyboards/generate")
    public Map<String, Object> generate(@RequestBody Map<String, Object> req) {
        List<Map<String, Object>> scenes = (List<Map<String, Object>>) req.getOrDefault("scenes", List.of());
        List<Map<String, Object>> shots = new ArrayList<>();
        int shotNo = 1;
        String[] shotTypes = {"远景", "中景", "近景", "特写"};
        String[] cameraMoves = {"固定机位", "缓慢推近", "轻微横移", "缓慢拉远"};
        for (Map<String, Object> scene : scenes) {
            int shotsPerScene = 2;
            for (int i = 0; i < shotsPerScene; i++) {
                shots.add(Map.of(
                        "shotNo", shotNo++,
                        "sceneId", String.valueOf(scene.getOrDefault("sceneId", "")),
                        "location", String.valueOf(scene.getOrDefault("location", "")),
                        "shotType", shotTypes[shotNo % shotTypes.length],
                        "cameraMove", cameraMoves[shotNo % cameraMoves.length],
                        "durationSec", 3 + ThreadLocalRandom.current().nextInt(4),
                        "prompt", "漫画风格，" + scene.getOrDefault("description", "") + "，" + cameraMoves[shotNo % cameraMoves.length]));
            }
        }
        return Map.of("dramaId", req.getOrDefault("dramaId", ""), "shots", shots, "totalShots", shots.size());
    }

    /** Mock 视频生成任务提交（生产版：模型路由网关 → 可灵/Seedance/Wan2.2） */
    @PostMapping("/shots/video")
    public Map<String, Object> submitVideo(@RequestBody Map<String, Object> req) {
        String taskId = "vt-" + UUID.randomUUID().toString().substring(0, 12);
        videoTasks.put(taskId, System.currentTimeMillis());
        return Map.of("taskId", taskId, "status", "SUBMITTED");
    }

    /** Mock 轮询：提交 1.5 秒后返回成功 */
    @GetMapping("/shots/video/{taskId}")
    public Map<String, Object> pollVideo(@PathVariable String taskId) {
        Long submittedAt = videoTasks.get(taskId);
        if (submittedAt == null) {
            return Map.of("taskId", taskId, "status", "NOT_FOUND");
        }
        if (System.currentTimeMillis() - submittedAt < 1500) {
            return Map.of("taskId", taskId, "status", "PROCESSING");
        }
        return Map.of(
                "taskId", taskId,
                "status", "SUCCESS",
                "videoUrl", "/oss/mock/shot_" + taskId + ".mp4",
                "resolution", "720p");
    }
}

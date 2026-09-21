package com.manju.compose;

import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 视频合成域（MVP Mock 版）。
 * 生产版：FFmpeg Worker 池（K8s Job 弹性伸缩）做音画对齐/字幕/转场/多规格导出；
 * 复杂合成降级走云剪辑 API（阿里云 IMS JSON 时间线）。本 Mock 模拟约 400ms 合成耗时。
 */
@RestController
@RequestMapping("/api/compose")
public class ComposeController {

    @PostMapping
    public Map<String, Object> compose(@RequestBody Map<String, Object> req) throws InterruptedException {
        Thread.sleep(400); // 模拟 FFmpeg 合成耗时
        List<Map<String, Object>> shots = (List<Map<String, Object>>) req.getOrDefault("shots", List.of());
        double totalDuration = shots.stream()
                .mapToDouble(s -> ((Number) s.getOrDefault("durationSec", 4)).doubleValue())
                .sum();
        return Map.of(
                "dramaId", req.getOrDefault("dramaId", ""),
                "outputUrl", "/oss/mock/drama_" + req.getOrDefault("dramaId", "x") + "_" + UUID.randomUUID().toString().substring(0, 8) + "_9x16.mp4",
                "durationSec", totalDuration,
                "resolution", "1080x1920",
                "shotCount", shots.size());
    }
}

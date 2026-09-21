package com.manju.voice;

import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 配音域（MVP Mock 版）。
 * 生产版：多角色 TTS + 音色克隆（商业：火山/Azure；开源：GPT-SoVITS/CosyVoice，走模型路由网关）。
 * 音频时长回填驱动镜头时长微调（偏差>15% 触发调整）；音色克隆须留存用户授权记录。
 */
@RestController
@RequestMapping("/api/voices")
public class VoiceController {

    @PostMapping("/generate")
    public Map<String, Object> generate(@RequestBody Map<String, Object> req) {
        String text = String.valueOf(req.getOrDefault("text", ""));
        String character = String.valueOf(req.getOrDefault("character", "旁白"));
        String emotion = String.valueOf(req.getOrDefault("emotion", "平静"));
        // Mock 时长：约 0.25 秒/字 + 随机抖动，模拟真实 TTS 时长回填
        double durationSec = Math.round((text.length() * 0.25 + ThreadLocalRandom.current().nextDouble(0.5)) * 10) / 10.0;
        return Map.of(
                "voiceId", "vo-" + UUID.randomUUID().toString().substring(0, 10),
                "sceneId", req.getOrDefault("sceneId", ""),
                "character", character,
                "emotion", emotion,
                "audioUrl", "/oss/mock/voice_" + character + "_" + System.currentTimeMillis() + ".mp3",
                "durationSec", durationSec,
                "subtitle", text);
    }
}

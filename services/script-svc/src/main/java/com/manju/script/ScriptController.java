package com.manju.script;

import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 剧本域（MVP Mock 版）。
 * 生产版：LLM 多轮生成（大纲→分幕→场次→对白），输出严格 JSON Schema，
 * 校验失败自动重试 ≤3 次；本 Mock 返回结构一致的 canned 剧本。
 */
@RestController
@RequestMapping("/api/scripts")
public class ScriptController {

    @PostMapping("/generate")
    public Map<String, Object> generate(@RequestBody Map<String, String> req) {
        String title = req.getOrDefault("title", "未命名漫剧");
        String topic = req.getOrDefault("topic", "");

        Map<String, Object> scene1 = Map.of(
                "sceneId", "sc-001",
                "location", "深夜便利店",
                "description", "雨夜，城市角落的便利店亮着孤灯，店主正在打瞌睡",
                "dialogues", List.of(
                        Map.of("character", "店主老周", "emotion", "慵懒", "text", "又是没人的一晚上……"),
                        Map.of("character", "神秘顾客", "emotion", "低沉", "text", "一把伞，能修的那种。")));

        Map<String, Object> scene2 = Map.of(
                "sceneId", "sc-002",
                "location", "便利店仓库",
                "description", "仓库深处透出微光，一排排旧物泛着奇异的蓝色光晕",
                "dialogues", List.of(
                        Map.of("character", "店主老周", "emotion", "惊讶", "text", "这些旧东西……在发光？"),
                        Map.of("character", "神秘顾客", "emotion", "平静", "text", "每件被修好的东西，都记得自己的故事。")));

        Map<String, Object> scene3 = Map.of(
                "sceneId", "sc-003",
                "location", "便利店门口",
                "description", "雨停了，晨光初现，老周握着那把修好的伞站在店门口",
                "dialogues", List.of(
                        Map.of("character", "店主老周", "emotion", "释然", "text", "原来我修的不是伞，是人心啊。")));

        return Map.of(
                "dramaId", req.getOrDefault("dramaId", ""),
                "title", title,
                "topic", topic,
                "characters", List.of("店主老周", "神秘顾客"),
                "scenes", List.of(scene1, scene2, scene3),
                "totalScenes", 3);
    }
}

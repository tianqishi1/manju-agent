package com.manju.topic;

import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 选题域（MVP Mock 版）。
 * 生产版：接入热点趋势抓取 + LLM 选题推荐（走模型路由网关），结果入库 t_topic。
 */
@RestController
@RequestMapping("/api/topics")
public class TopicController {

    private static final List<Map<String, Object>> SEED_TOPICS = List.of(
            Map.of("id", 1L, "title", "深夜便利店的一千零一夜", "genre", "都市奇幻"),
            Map.of("id", 2L, "title", "外卖骑手的平行时空", "genre", "科幻"),
            Map.of("id", 3L, "title", "奶奶的武林秘籍", "genre", "家庭喜剧"),
            Map.of("id", 4L, "title", "最后一个修伞人", "genre", "怀旧情感"),
            Map.of("id", 5L, "title", "猫主子的复仇计划", "genre", "萌宠搞笑"));

    private final AtomicLong idGen = new AtomicLong(100);

    @GetMapping
    public List<Map<String, Object>> list() {
        return SEED_TOPICS;
    }

    /** Mock LLM 选题推荐：生产版调用模型路由网关的 LLM 适配器 */
    @PostMapping("/recommend")
    public Map<String, Object> recommend(@RequestBody Map<String, String> req) {
        String genre = req.getOrDefault("genre", "都市奇幻");
        String[] hooks = {"意外获得超能力", "发现了家族秘密", "遇上会说话的动物", "时间循环了一天", "捡到一部来自未来的手机"};
        String hook = hooks[(int) (System.currentTimeMillis() % hooks.length)];
        return Map.of(
                "id", idGen.incrementAndGet(),
                "title", genre + "新番：" + hook,
                "genre", genre,
                "source", "LLM_RECOMMEND",
                "hook", hook);
    }
}

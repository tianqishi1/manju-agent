package com.manju.asset;

import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 素材域（MVP Mock 版）。
 * 生产版：① 网络素材检索（版权状态标注 UNKNOWN 不可商用）② AI 生成角色设定卡
 * → 组装「角色资产包」(设定卡+参考图集) 供分镜图生成复用，保证角色一致性。
 * 产物 URL 生成后立即转存 OSS（外部 URL 有时效）。
 */
@RestController
@RequestMapping("/api/assets")
public class AssetController {

    @PostMapping("/prepare")
    public Map<String, Object> prepare(@RequestBody Map<String, String> req) {
        String title = req.getOrDefault("title", "");
        return Map.of(
                "dramaId", req.getOrDefault("dramaId", ""),
                "characters", List.of(
                        Map.of(
                                "name", "店主老周",
                                "desc", "50岁便利店店主，微胖，围裙，眼神温和",
                                "assetPackId", "pack-" + UUID.randomUUID().toString().substring(0, 8),
                                "refImages", List.of("/oss/mock/char_zhou_front.png", "/oss/mock/char_zhou_side.png", "/oss/mock/char_zhou_expr.png"),
                                "loraModelId", ""),
                        Map.of(
                                "name", "神秘顾客",
                                "desc", "年龄不详，黑色长风衣，撑一把破旧油纸伞",
                                "assetPackId", "pack-" + UUID.randomUUID().toString().substring(0, 8),
                                "refImages", List.of("/oss/mock/char_customer_front.png", "/oss/mock/char_customer_side.png"),
                                "loraModelId", "")),
                "scenes", List.of(
                        Map.of("name", "深夜便利店", "refImage", "/oss/mock/scene_store.png"),
                        Map.of("name", "便利店仓库", "refImage", "/oss/mock/scene_warehouse.png"),
                        Map.of("name", "便利店门口·清晨", "refImage", "/oss/mock/scene_door.png")),
                "voiceBindings", Map.of(
                        "店主老周", "voice-male-warm-01",
                        "神秘顾客", "voice-male-low-02"),
                "title", title);
    }
}

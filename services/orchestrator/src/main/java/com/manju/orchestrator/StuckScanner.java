package com.manju.orchestrator;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.List;

/** 卡死扫描：每分钟检查 RUNNING 且超阈值无更新的剧集，落 stuck_warning 事件（去重：已警告过则不重复）。 */
@Component
public class StuckScanner {

    private static final Logger log = LoggerFactory.getLogger(StuckScanner.class);

    private final DramaRepository dramas;
    private final DramaEventRepository events;
    private final OpsController ops;

    @Value("${ops.stuck-after-seconds:300}")
    private long stuckAfterSeconds;

    public StuckScanner(DramaRepository dramas, DramaEventRepository events, OpsController ops) {
        this.dramas = dramas;
        this.events = events;
        this.ops = ops;
    }

    @Scheduled(fixedDelay = 60_000, initialDelay = 60_000)
    public void scan() {
        List<Drama> stuck = ops.findStuck(stuckAfterSeconds);
        for (Drama d : stuck) {
            List<DramaEvent> evs = events.findByDramaIdOrderByIdAsc(d.getId());
            boolean alreadyWarned = !evs.isEmpty()
                    && "stuck_warning".equals(evs.get(evs.size() - 1).getStage());
            if (alreadyWarned) continue;
            DramaEvent e = new DramaEvent();
            e.setDramaId(d.getId());
            e.setStage("stuck_warning");
            e.setMessage(String.format("剧集 RUNNING 超过 %ds 无进度更新，疑似卡死，请排查（生产版：触发告警+自动补偿）",
                    java.time.Duration.between(d.getUpdatedAt(), LocalDateTime.now()).getSeconds()));
            events.save(e);
            d.setUpdatedAt(LocalDateTime.now()); // 重置计时，避免每分钟重复警告
            dramas.save(d);
            log.warn("drama {} suspected stuck", d.getId());
        }
    }
}

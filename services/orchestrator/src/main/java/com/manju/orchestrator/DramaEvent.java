package com.manju.orchestrator;

import jakarta.persistence.*;

import java.time.LocalDateTime;

/** 剧集事件流水：编排层每个阶段完成/失败均落一条，供前端时间线与审计 */
@Entity
public class DramaEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long dramaId;
    private String stage;
    @Lob
    @Column(length = 10000)
    private String message;
    private LocalDateTime createdAt = LocalDateTime.now();

    public Long getId() { return id; }
    public Long getDramaId() { return dramaId; }
    public void setDramaId(Long dramaId) { this.dramaId = dramaId; }
    public String getStage() { return stage; }
    public void setStage(String stage) { this.stage = stage; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public LocalDateTime getCreatedAt() { return createdAt; }
}

package com.manju.orchestrator;

import jakarta.persistence.*;

/** 子任务表：镜头视频/配音/合成粒度的状态，支撑断点续作与失败重跑（MVP 简化为 upsert 模型） */
@Entity
@Table(uniqueConstraints = @UniqueConstraint(columnNames = {"dramaId", "type", "refId"}))
public class Subtask {

    public enum Status { PENDING, RUNNING, SUCCESS, FAILED }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long dramaId;
    private String type;   // SHOT_VIDEO / VOICE / COMPOSE
    private String refId;  // shotNo / sceneId / dramaId
    @Enumerated(EnumType.STRING)
    private Status status = Status.PENDING;
    private String artifactUrl;

    public Long getId() { return id; }
    public Long getDramaId() { return dramaId; }
    public void setDramaId(Long dramaId) { this.dramaId = dramaId; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public String getRefId() { return refId; }
    public void setRefId(String refId) { this.refId = refId; }
    public Status getStatus() { return status; }
    public void setStatus(Status status) { this.status = status; }
    public String getArtifactUrl() { return artifactUrl; }
    public void setArtifactUrl(String artifactUrl) { this.artifactUrl = artifactUrl; }
}

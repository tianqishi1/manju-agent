package com.manju.orchestrator;

import jakarta.persistence.*;

import java.time.LocalDateTime;

/** 剧集主表：业务总状态机（生成 DAG 内部状态由 LangGraph checkpoint 管理） */
@Entity
public class Drama {

    public enum Status { DRAFT, RUNNING, AWAIT_REVIEW, COMPLETED, FAILED, REJECTED }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;
    private String topic;

    @Enumerated(EnumType.STRING)
    private Status status = Status.DRAFT;

    @Lob
    @Column(length = 100000)
    private String scriptJson;

    /** 当前待审类型：SCRIPT（剧本人审）/ STYLE（首镜头画风审核），非待审时为 null */
    private String reviewKind;
    /** 画风审核的预览视频 URL */
    private String previewUrl;

    private String outputUrl;
    private LocalDateTime createdAt = LocalDateTime.now();
    private LocalDateTime updatedAt = LocalDateTime.now();

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getTopic() { return topic; }
    public void setTopic(String topic) { this.topic = topic; }
    public Status getStatus() { return status; }
    public void setStatus(Status status) { this.status = status; }
    public String getScriptJson() { return scriptJson; }
    public void setScriptJson(String scriptJson) { this.scriptJson = scriptJson; }
    public String getReviewKind() { return reviewKind; }
    public void setReviewKind(String reviewKind) { this.reviewKind = reviewKind; }
    public String getPreviewUrl() { return previewUrl; }
    public void setPreviewUrl(String previewUrl) { this.previewUrl = previewUrl; }
    public String getOutputUrl() { return outputUrl; }
    public void setOutputUrl(String outputUrl) { this.outputUrl = outputUrl; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}

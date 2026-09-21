package com.manju.orchestrator;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/** 调用 Python LangGraph 编排层（异步，fire-and-forget；生产版换 RocketMQ 任务消息驱动） */
@Component
public class AgentClient {

    private static final Logger log = LoggerFactory.getLogger(AgentClient.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Value("${agent.url:http://localhost:8000}")
    private String agentUrl;

    @Async
    public void runDramaAsync(Long dramaId, String title, String topic) {
        post(agentUrl + "/v1/dramas/" + dramaId + "/run", java.util.Map.of(
                "dramaId", String.valueOf(dramaId), "title", title, "topic", topic));
    }

    @Async
    public void approveDramaAsync(Long dramaId, boolean approved, String editedScript) {
        java.util.Map<String, Object> body = new java.util.HashMap<>();
        body.put("approved", approved);
        if (editedScript != null && !editedScript.isBlank()) {
            body.put("editedScript", editedScript);
        }
        post(agentUrl + "/v1/dramas/" + dramaId + "/approve", body);
    }

    private void post(String url, Object body) {
        try {
            String json = MAPPER.writeValueAsString(body);
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(10))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json))
                    .build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            log.info("agent call {} -> {}", url, resp.statusCode());
        } catch (Exception e) {
            log.error("agent call failed: {} ({})", url, e.getMessage());
        }
    }
}

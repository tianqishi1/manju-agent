package com.manju.orchestrator;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface SubtaskRepository extends JpaRepository<Subtask, Long> {
    List<Subtask> findByDramaIdOrderByIdAsc(Long dramaId);
    Optional<Subtask> findByDramaIdAndTypeAndRefId(Long dramaId, String type, String refId);
    List<Subtask> findByStatus(Subtask.Status status);
}

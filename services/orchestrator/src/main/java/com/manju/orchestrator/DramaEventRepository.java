package com.manju.orchestrator;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface DramaEventRepository extends JpaRepository<DramaEvent, Long> {
    List<DramaEvent> findByDramaIdOrderByIdAsc(Long dramaId);
}

package com.manju.orchestrator;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface DramaRepository extends JpaRepository<Drama, Long> {
    List<Drama> findTop20ByOrderByIdDesc();
}

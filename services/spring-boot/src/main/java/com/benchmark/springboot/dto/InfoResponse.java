package com.benchmark.springboot.dto;

import java.util.List;

// Test 1: medium JSON (8 fields, varying types) + a custom response header.
public record InfoResponse(
        String id,
        String name,
        int count,
        double ratio,
        boolean active,
        List<String> tags,
        String createdAt,
        Nested nested) {}

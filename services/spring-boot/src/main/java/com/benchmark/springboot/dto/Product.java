package com.benchmark.springboot.dto;

import java.util.List;

// Test 3: typed parse of the upstream's static product payload.
public record Product(
        String id,
        String title,
        double price,
        boolean inStock,
        List<String> tags,
        double rating,
        String description,
        Vendor vendor) {}

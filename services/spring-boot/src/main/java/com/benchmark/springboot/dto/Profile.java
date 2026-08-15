package com.benchmark.springboot.dto;

// Test 4: JWT id + a Postgres users row.
public record Profile(
        String id, String name, String email, String address, String city, String country) {}

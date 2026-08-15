package com.benchmark.springboot.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

// Test 2: JWT-authenticated POST, validated 5-field body.
public record MovieIn(
        @NotBlank String title,
        @NotNull Integer year,
        @NotBlank String director,
        @NotBlank String genre,
        @NotNull Double rating) {}

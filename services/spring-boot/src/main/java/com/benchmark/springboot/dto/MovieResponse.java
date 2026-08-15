package com.benchmark.springboot.dto;

public record MovieResponse(
        String title,
        int year,
        String director,
        String genre,
        double rating,
        String id,
        UserRef user) {}

package com.benchmark.springboot.web;

import com.benchmark.springboot.dto.ErrorResponse;
import com.benchmark.springboot.dto.InfoResponse;
import com.benchmark.springboot.dto.MovieIn;
import com.benchmark.springboot.dto.MovieResponse;
import com.benchmark.springboot.dto.Nested;
import com.benchmark.springboot.dto.Product;
import com.benchmark.springboot.dto.Profile;
import com.benchmark.springboot.dto.UserRef;
import com.benchmark.springboot.jwt.JwtService;
import io.jsonwebtoken.Claims;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class BenchController {

    private static final Logger log = LoggerFactory.getLogger(BenchController.class);

    private static final String GET_USER_SQL =
            "SELECT id, name, email, address, city, country FROM users WHERE id = ?";

    private final JwtService jwtService;
    private final JdbcTemplate jdbcTemplate;
    private final RestClient upstreamClient;

    public BenchController(JwtService jwtService, JdbcTemplate jdbcTemplate, RestClient upstreamClient) {
        this.jwtService = jwtService;
        this.jdbcTemplate = jdbcTemplate;
        this.upstreamClient = upstreamClient;
    }

    @GetMapping("/info")
    public ResponseEntity<InfoResponse> info() {
        var body = new InfoResponse(
                "info-1",
                "Benchmark Info",
                42,
                3.14159,
                true,
                List.of("alpha", "beta", "gamma"),
                "2026-01-01T00:00:00Z",
                new Nested(2, "nested"));
        return ResponseEntity.ok()
                .header("x-response-id", UUID.randomUUID().toString())
                .body(body);
    }

    @PostMapping("/movies")
    public ResponseEntity<MovieResponse> createMovie(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization,
            @Valid @RequestBody MovieIn in) {
        Claims claims = jwtService.verifyOrThrow(authorization);
        var movie = new MovieResponse(
                in.title(),
                in.year(),
                in.director(),
                in.genre(),
                in.rating(),
                UUID.randomUUID().toString(),
                new UserRef(claims.getSubject(), claims.get("name", String.class)));
        return ResponseEntity.status(HttpStatus.CREATED).body(movie);
    }

    @GetMapping("/catalog")
    public ResponseEntity<?> catalog() {
        Product product;
        try {
            product = upstreamClient.get().uri("/data").retrieve().body(Product.class);
        } catch (Exception e) {
            log.warn("upstream call failed", e);
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(new ErrorResponse("upstream unavailable"));
        }
        if (product == null) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(new ErrorResponse("bad upstream response"));
        }
        return ResponseEntity.ok(product);
    }

    @GetMapping("/users/me")
    public ResponseEntity<?> me(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization) {
        Claims claims = jwtService.verifyOrThrow(authorization);
        try {
            Profile profile = jdbcTemplate.queryForObject(
                    GET_USER_SQL,
                    (rs, rowNum) -> new Profile(
                            rs.getString("id"),
                            rs.getString("name"),
                            rs.getString("email"),
                            rs.getString("address"),
                            rs.getString("city"),
                            rs.getString("country")),
                    claims.getSubject());
            return ResponseEntity.ok(profile);
        } catch (EmptyResultDataAccessException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(new ErrorResponse("user not found"));
        }
    }
}

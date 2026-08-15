package com.benchmark.springboot.jwt;

import com.benchmark.springboot.config.AppProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.JwtParser;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Service;

// Verifies the shared HS256 token every framework in this benchmark mints the
// same way (see loadtest/lib/common.js) — same contract as PyJWT elsewhere.
@Service
public class JwtService {

    private final JwtParser parser;

    public JwtService(AppProperties props) {
        SecretKey key = Keys.hmacShaKeyFor(props.jwtSecret().getBytes(StandardCharsets.UTF_8));
        // JwtParser is immutable and thread-safe once built — build it once
        // here rather than per request, since verify() runs on every
        // authenticated request in a service being measured for req/s.
        this.parser = Jwts.parser().verifyWith(key).build();
    }

    // Throws instead of returning null so both authenticated endpoints share
    // one 401 mapping (see GlobalExceptionHandler) instead of duplicating the
    // null-check-and-401 dance.
    public Claims verifyOrThrow(String authorizationHeader) {
        if (authorizationHeader == null || !authorizationHeader.startsWith("Bearer ")) {
            throw new UnauthorizedException();
        }
        String token = authorizationHeader.substring("Bearer ".length()).trim();
        Claims claims;
        try {
            claims = parser.parseSignedClaims(token).getPayload();
        } catch (JwtException | IllegalArgumentException e) {
            throw new UnauthorizedException();
        }
        if (claims.getSubject() == null || claims.getSubject().isBlank()) {
            throw new UnauthorizedException();
        }
        return claims;
    }
}

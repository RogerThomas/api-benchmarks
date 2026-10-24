// Gin benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Nested struct {
	Level int    `json:"level"`
	Label string `json:"label"`
}

type Info struct {
	ID        string   `json:"id"`
	Name      string   `json:"name"`
	Count     int      `json:"count"`
	Ratio     float64  `json:"ratio"`
	Active    bool     `json:"active"`
	Tags      []string `json:"tags"`
	CreatedAt string   `json:"createdAt"`
	Nested    Nested   `json:"nested"`
}

// binding:"required": a missing field is a 400, not a silent zero value.
type MovieIn struct {
	Title    string  `json:"title" binding:"required"`
	Year     int     `json:"year" binding:"required"`
	Director string  `json:"director" binding:"required"`
	Genre    string  `json:"genre" binding:"required"`
	Rating   float64 `json:"rating" binding:"required"`
}

type User struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

// The JWT's claims; a token missing sub or name is rejected as invalid.
type Claims struct {
	Name string `json:"name"`
	jwt.RegisteredClaims
}

type Movie struct {
	MovieIn
	ID   string `json:"id"`
	User User   `json:"user"`
}

type Vendor struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type Product struct {
	ID          string   `json:"id"`
	Title       string   `json:"title"`
	Price       float64  `json:"price"`
	InStock     bool     `json:"inStock"`
	Tags        []string `json:"tags"`
	Rating      float64  `json:"rating"`
	Description string   `json:"description"`
	Vendor      Vendor   `json:"vendor"`
}

type Profile struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Email   string `json:"email"`
	Address string `json:"address"`
	City    string `json:"city"`
	Country string `json:"country"`
}

func main() {
	secret := []byte(os.Getenv("JWT_SECRET"))
	upstreamURL := os.Getenv("UPSTREAM_URL")
	upstreamKey := os.Getenv("UPSTREAM_API_KEY")
	// HTTP client pool capped at 64 to match the other frameworks' outbound
	// budget (Bun BUN_CONFIG_MAX_HTTP_REQUESTS=64). Keep-alive reuse also avoids
	// churning connections into TIME_WAIT and exhausting ephemeral ports.
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.MaxConnsPerHost = 64
	transport.MaxIdleConns = 64
	transport.MaxIdleConnsPerHost = 64
	transport.IdleConnTimeout = 90 * time.Second
	client := &http.Client{Transport: transport}

	// DB pool capped at 64 to match the other frameworks (Python db_pool_size=64);
	// pgx otherwise defaults to ~NumCPU, which would starve/skew test 4.
	dsn := fmt.Sprintf("postgres://%s:%s@%s:%s/%s",
		os.Getenv("DB_USER"), os.Getenv("DB_PASSWORD"),
		os.Getenv("DB_HOST"), os.Getenv("DB_PORT"), os.Getenv("DB_NAME"))
	dbcfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		panic(err)
	}
	dbcfg.MaxConns = 64
	pool, err := pgxpool.NewWithConfig(context.Background(), dbcfg)
	if err != nil {
		panic(err)
	}
	defer pool.Close()

	keyFunc := func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, jwt.ErrSignatureInvalid
		}
		return secret, nil
	}

	// authenticate verifies the bearer JWT, answering 401 itself on failure.
	authenticate := func(c *gin.Context) (User, bool) {
		tokenStr := strings.TrimSpace(strings.TrimPrefix(c.GetHeader("Authorization"), "Bearer "))
		var claims Claims
		token, err := jwt.ParseWithClaims(tokenStr, &claims, keyFunc)
		if err != nil || !token.Valid || claims.Subject == "" || claims.Name == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return User{}, false
		}
		return User{ID: claims.Subject, Name: claims.Name}, true
	}

	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	r.GET("/info", func(c *gin.Context) {
		c.Header("x-response-id", uuid.NewString())
		c.JSON(http.StatusOK, Info{
			ID:        "info-1",
			Name:      "Benchmark Info",
			Count:     42,
			Ratio:     3.14159,
			Active:    true,
			Tags:      []string{"alpha", "beta", "gamma"},
			CreatedAt: "2026-01-01T00:00:00Z",
			Nested:    Nested{Level: 2, Label: "nested"},
		})
	})

	r.POST("/movies", func(c *gin.Context) {
		user, ok := authenticate(c)
		if !ok {
			return
		}

		var in MovieIn
		if err := c.ShouldBindJSON(&in); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid body"})
			return
		}
		movie := Movie{
			MovieIn: in,
			ID:      uuid.NewString(),
			User:    user,
		}
		c.JSON(http.StatusCreated, movie)
	})

	r.GET("/catalog", func(c *gin.Context) {
		req, _ := http.NewRequest(http.MethodGet, upstreamURL+"/data", nil)
		req.Header.Set("Authorization", "Bearer "+upstreamKey)
		resp, err := client.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"error": "upstream unavailable"})
			return
		}
		defer resp.Body.Close()
		var product Product
		if err := json.NewDecoder(resp.Body).Decode(&product); err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"error": "bad upstream response"})
			return
		}
		c.JSON(http.StatusOK, product)
	})

	r.GET("/users/me", func(c *gin.Context) {
		user, ok := authenticate(c)
		if !ok {
			return
		}

		var p Profile
		err := pool.QueryRow(
			c.Request.Context(),
			"SELECT id, name, email, address, city, country FROM users WHERE id = $1",
			user.ID,
		).
			Scan(&p.ID, &p.Name, &p.Email, &p.Address, &p.City, &p.Country)
		if errors.Is(err, pgx.ErrNoRows) {
			c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		c.JSON(http.StatusOK, p)
	})

	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}
	r.Run(":" + port)
}

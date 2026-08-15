// Gin benchmark app — tests 1 (GET info) and 2 (authenticated POST movie).
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
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

type MovieIn struct {
	Title    string  `json:"title"`
	Year     int     `json:"year"`
	Director string  `json:"director"`
	Genre    string  `json:"genre"`
	Rating   float64 `json:"rating"`
}

type User struct {
	ID   string `json:"id"`
	Name string `json:"name"`
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

const getUserSQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"

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
		authz := c.GetHeader("Authorization")
		tokenStr := strings.TrimSpace(strings.TrimPrefix(authz, "Bearer "))
		token, err := jwt.Parse(tokenStr, keyFunc)
		if err != nil || !token.Valid {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return
		}
		claims := token.Claims.(jwt.MapClaims)

		var in MovieIn
		if err := c.ShouldBindJSON(&in); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid body"})
			return
		}
		movie := Movie{
			MovieIn: in,
			ID:      uuid.NewString(),
			User:    User{ID: claims["sub"].(string), Name: claims["name"].(string)},
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
		authz := c.GetHeader("Authorization")
		tokenStr := strings.TrimSpace(strings.TrimPrefix(authz, "Bearer "))
		token, err := jwt.Parse(tokenStr, keyFunc)
		if err != nil || !token.Valid {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return
		}
		sub := token.Claims.(jwt.MapClaims)["sub"].(string)

		var p Profile
		err = pool.QueryRow(c.Request.Context(), getUserSQL, sub).
			Scan(&p.ID, &p.Name, &p.Email, &p.Address, &p.City, &p.Country)
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
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

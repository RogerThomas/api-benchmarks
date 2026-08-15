// Extremely fast upstream: returns a static JSON payload from /data, gated by a
// static bearer API key (service-to-service auth). /health is unauthenticated.
// The body is a precomputed &'static str — no per-request serialization.
use axum::{
    extract::State,
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::get,
    Router,
};

const PAYLOAD: &str = r#"{"id":"prod-1","title":"Mechanical Keyboard","price":129.99,"inStock":true,"tags":["electronics","peripherals","keyboard"],"rating":4.7,"description":"A tactile mechanical keyboard with hot-swappable switches.","vendor":{"id":"vendor-9","name":"KeyCo"}}"#;

#[tokio::main]
async fn main() {
    let api_key = std::env::var("UPSTREAM_API_KEY").unwrap_or_default();
    let app = Router::new()
        .route("/data", get(data))
        .route("/health", get(|| async { "ok" }))
        .with_state(api_key);
    let port = std::env::var("PORT").unwrap_or_else(|_| "8000".to_string());
    let addr = format!("0.0.0.0:{port}");

    // Retry the bind a few times: on a container restart the previous instance
    // may still hold the port for a moment. Panicking immediately (the old
    // behaviour) made the upstream die silently on that race.
    let listener = loop {
        match tokio::net::TcpListener::bind(&addr).await {
            Ok(l) => break l,
            Err(e) => {
                eprintln!("upstream: bind {addr} failed: {e}; retrying in 500ms");
                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
            }
        }
    };
    println!("upstream listening on {addr}");

    // Log instead of unwrap-panicking so a fatal serve error is visible in logs.
    if let Err(e) = axum::serve(listener, app).await {
        eprintln!("upstream: serve error: {e}");
    }
}

async fn data(State(api_key): State<String>, headers: HeaderMap) -> Response {
    let auth = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    let token = auth.strip_prefix("Bearer ").unwrap_or("").trim();
    if token != api_key {
        return (
            StatusCode::UNAUTHORIZED,
            [(header::CONTENT_TYPE, "application/json")],
            r#"{"error":"invalid api key"}"#,
        )
            .into_response();
    }
    ([(header::CONTENT_TYPE, "application/json")], PAYLOAD).into_response()
}

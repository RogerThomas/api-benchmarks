import crypto from "k6/crypto";
import encoding from "k6/encoding";

// Shared k6 options driven by env. Each test runs for DURATION (k6 duration
// string, e.g. "10s"/"30s"), holding VUS constant.
export function options() {
  const duration = __ENV.DURATION || "10s";
  const vus = parseInt(__ENV.VUS || "50", 10);
  return {
    discardResponseBodies: false,
    summaryTrendStats: ["avg", "min", "med", "max", "p(50)", "p(75)", "p(90)", "p(99)"],
    scenarios: {
      load: {
        executor: "constant-vus",
        vus: vus,
        duration: duration,
      },
    },
  };
}

// Mint an HS256 JWT in-process from the shared secret — no token plumbing needed.
function b64url(str) {
  return encoding.b64encode(str, "rawurl");
}

export function makeToken() {
  const secret = __ENV.JWT_SECRET;
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = b64url(
    JSON.stringify({ sub: "user-123", name: "Ada Lovelace", iat: 1735689600 }),
  );
  const signingInput = `${header}.${payload}`;
  const sig = crypto.hmac("sha256", secret, signingInput, "base64rawurl");
  return `${signingInput}.${sig}`;
}

// Build a clean per-run summary from k6's end-of-test data and write it to a
// file the orchestrator (run.sh) later merges into the final report.
export function summarize(data) {
  const fw = __ENV.FRAMEWORK;
  const test = __ENV.TEST;
  const dur = data.metrics.http_req_duration.values;
  const reqs = data.metrics.http_reqs.values;
  const failed = data.metrics.http_req_failed
    ? data.metrics.http_req_failed.values
    : { passes: 0, fails: 0 };
  const durationMs = data.state.testRunDurationMs;

  const run = {
    framework: fw,
    test: test,
    attempt: parseInt(__ENV.ATTEMPT || "1", 10),
    durationSec: parseInt(__ENV.DURATION || "10s", 10),
    vus: parseInt(__ENV.VUS || "50", 10),
    totalRequests: reqs.count,
    failedRate: failed.rate || 0,
    totalTimeSec: durationMs / 1000,
    reqsPerSec: reqs.rate,
    latencyMs: {
      avg: dur.avg,
      min: dur.min,
      med: dur.med,
      max: dur.max,
      p50: dur["p(50)"],
      p75: dur["p(75)"],
      p90: dur["p(90)"],
      p99: dur["p(99)"],
    },
  };

  const dir = __ENV.RESULTS_DIR || "/results";
  const out = {};
  out[`${dir}/attempt-${fw}-${test}-${run.attempt}.json`] = JSON.stringify(run, null, 2);
  out.stdout = `\n  ${fw}/${test} attempt ${run.attempt}: ${run.reqsPerSec.toFixed(0)} req/s, mean ${run.latencyMs.avg.toFixed(2)}ms, p99 ${run.latencyMs.p99.toFixed(2)}ms\n`;
  return out;
}

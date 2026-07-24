# FastAPI & Backend Interview Prep — 100 Questions
**Target profile:** 6 yrs SWE · Python · Django · FastAPI · Docker/Git
**Built from source research on:** 23 July 2026

---

## What the research actually showed

I checked current interview guides, senior challenge banks, production post-mortems, and the FastAPI repo before writing this. Four patterns dominate, and they should shape how you allocate prep time:

**1. Async is the single biggest filter — and it's a *conceptual* filter, not a syntax one.** A hiring manager rejected a candidate with eight years of experience after a 45-minute screen with a three-word note: "Couldn't explain asyncio." Not couldn't use it — couldn't explain what the event loop does and why it matters for I/O-bound services. Industry data attributes roughly two-thirds of API performance problems to improper async implementation. **Section 1 is the highest-yield section in this document.** If you prep nothing else properly, prep that.

**2. The specific bug they probe for is blocking the event loop.** Every production post-mortem I read described the same failure: a sync call inside an `async def` route — sync DB driver, `time.sleep`, `requests` — invisible at 1 req/s in dev, catastrophic at 200 in prod. Interviewers ask it as "your async endpoint got slower under load, why?" Have the diagnosis and the two fixes ready cold.

**3. Senior challenges are systems-flavored, not toy-flavored.** The senior banks ask for things like Redis-backed sliding-window rate limiting with correct `X-RateLimit-*` headers, background file processing with progress tracking and webhooks, circuit breakers with exponential backoff, and cursor pagination. Not "reverse a string."

**4. Offers die in system design.** For senior Python loops, most rejections land in the system design or live coding stage — not the fundamentals screen. Section 8 deserves real time.

**Version currency (mid-2026):** FastAPI is in the 0.13x line, Pydantic is on 2.13.x, and Starlette moved to the 1.0 range. FastAPI has been stripping out Pydantic v1 internals, and `pydantic.v1` compatibility raised a deprecation warning as of 0.127.0. `@app.on_event` is deprecated — use `lifespan`. SQLAlchemy 2.0 removed the legacy `.query()` pattern. Python 3.12/3.13 is the practical sweet spot; free-threaded 3.13 is interesting but not a production answer yet. **Saying `on_event` or `.query()` in an interview dates you by two years.**

---

## Section 1 — Async & Concurrency
### The make-or-break section. Prep this until it's reflexive.

1. **Explain the asyncio event loop as if to a colleague who only knows threads.**
   → Single thread, cooperative multitasking. Tasks voluntarily yield at `await` points; the loop runs whichever task is ready. No preemption — a task that never yields owns the thread until it finishes. The restaurant metaphor works well: one waiter, many tables; the waiter is useful only because he doesn't stand and wait while the kitchen cooks.

2. **What actually happens when FastAPI receives a request to an `async def` route vs a `def` route?**
   → `async def` runs directly on the event loop. Plain `def` is dispatched to an anyio worker threadpool so it can't block the loop. **The threadpool is bounded** (default around 40 workers) — that ceiling is a real capacity limit people forget.

3. **Is it always better to use `async def`? Argue the other side.**
   → No. If your work is sync-blocking (legacy driver, sync SDK, CPU work), plain `def` is *correct* — FastAPI threads it for you. Taking the escape hatch isn't cheating, it's engineering. `async def` with blocking work inside is strictly worse than `def`.

4. **A single `time.sleep(2)` sits in one handler. What's the blast radius?**
   → Every request on that worker stalls for two seconds — the health check, the login route, the 10ms lookups, all of them. This is the canonical answer they're listening for.

5. **Your `async def` endpoints got *slower* under load. Walk me through the diagnosis.**
   → Classic signature: throughput plateaus early, latency balloons, but CPU sits at 50–60% — no obvious overload. That gap between moderate CPU and stalled throughput is the tell. Find blocking calls: `asyncio` debug mode (`PYTHONASYNCIODEBUG=1`) logs slow callbacks, `py-spy dump` shows what the loop thread is actually doing, or audit for sync drivers in async routes.

6. **Name the four categories of blocking work and the right fix for each.**
   → (a) Sync I/O → async driver, or `run_in_threadpool` / `asyncio.to_thread`. (b) CPU-bound → `ProcessPoolExecutor` or an external worker. (c) Legacy sync libraries → thread them. (d) Long-running jobs → don't do them in the request path at all; queue them.

7. **`asyncio.gather` vs `asyncio.TaskGroup` — which and why?**
   → `TaskGroup` (3.11+) is the modern choice: structured concurrency, cancels siblings on failure, propagates as `ExceptionGroup`. `gather(return_exceptions=True)` silently collects failures — fine when you want partial results, dangerous when you don't. Say you'd pick based on whether a partial failure should abort the batch.

8. **How do you cap concurrency when fanning out 500 outbound calls?**
   → `asyncio.Semaphore` bounding in-flight requests, a shared `httpx.AsyncClient` with connection limits, timeouts on every call, and backoff on 429/5xx. Unbounded `gather` over 500 URLs is a self-inflicted DDoS on your own dependency.

9. **How do you add a timeout to an async operation, and what happens to the coroutine?**
   → `asyncio.timeout()` (3.11+) or `wait_for`. It raises `CancelledError` inside the coroutine at its next await point — cancellation is cooperative, so a coroutine that never yields can't be cancelled. Cleanup belongs in `finally` or an async context manager.

10. **Explain the GIL, and when it stops mattering for your service.**
    → GIL serializes Python bytecode, so threads don't give CPU parallelism. Irrelevant for I/O-bound work (threads and asyncio both fine — the GIL is released during I/O waits). Relevant for CPU-bound work → processes. Mention free-threaded 3.13 as awareness, not as a production recommendation.

11. **`multiprocessing` vs `threading` vs `asyncio` — pick one for: (a) 10k API calls, (b) resizing 10k images, (c) one legacy sync SDK call per request.**
    → (a) asyncio with a semaphore. (b) process pool. (c) plain `def` route, let FastAPI thread it.

12. **What is a coroutine, and how does it differ from a generator?**
    → Both are suspendable via the same underlying machinery; coroutines are driven by an event loop and suspend on `await` rather than producing values on `yield`. Calling a coroutine function returns a coroutine object that does nothing until awaited or scheduled — **forgetting to await is a top-5 async bug**, and it fails silently.

13. **What's a "fire and forget" task in asyncio, and what's the trap?**
    → `asyncio.create_task()` without keeping a reference — the task can be garbage collected mid-flight, and exceptions vanish silently. Hold a reference in a module-level set and discard on completion, or use a TaskGroup.

14. **`BackgroundTasks` vs Celery/Arq/RQ — when is each correct?**
    → `BackgroundTasks` runs in-process after the response is sent: fine for a fast, best-effort side effect (audit log, cache warm). It is **not durable** — a pod restart loses the work, and there's no retry, no visibility, no scheduling. Anything that matters goes on a real queue.

15. **Explain backpressure. How do you apply it in an async service?**
    → When arrival rate exceeds service rate, unbounded queues turn into unbounded latency and OOM. Apply bounded queues, concurrency limits, load shedding with 429/503, and reject-fast rather than queue-forever. The senior insight: **a timeout without a concurrency limit just moves the failure.**

16. **How do you stream an LLM/long response to a client through FastAPI?**
    → `StreamingResponse` with an async generator, or SSE. Handle client disconnect (`await request.is_disconnected()`), disable proxy buffering (`proxy_buffering off` in nginx), and remember every open stream holds a connection and a worker slot — factor that into capacity planning.

---

## Section 2 — FastAPI Core, DI & Pydantic

17. **What is ASGI and how does it differ from WSGI?**
    → WSGI is a synchronous single-callable interface: one request, one response, blocking. ASGI is async and event-driven, with a scope/receive/send protocol that supports long-lived connections — WebSockets, SSE, HTTP/2 server push. FastAPI is ASGI via Starlette.

18. **What is FastAPI actually made of?**
    → Starlette for the ASGI/routing/middleware layer, Pydantic for validation and serialization, and FastAPI's own dependency injection and OpenAPI generation on top. Knowing the seam matters: routing/middleware questions are really Starlette questions.

19. **Explain the dependency injection system. Why is it better than decorators or globals?**
    → `Depends()` resolves a callable per request, supports sub-dependencies, and — critically — is **overridable in tests** via `app.dependency_overrides`. That testability is the argument. Modern style is `Annotated[Session, Depends(get_db)]`.

20. **If the same dependency appears three times in one request's tree, how many times does it run?**
    → Once — results are cached per request. Pass `use_cache=False` to force re-execution. Follow-up they like: why would you ever want that? (Non-idempotent dependencies, or fresh timestamps.)

21. **Explain dependencies with `yield`. When does teardown run?**
    → Code before `yield` runs on the way in, code after runs on the way out, after the response. Standard pattern for DB sessions and any resource needing cleanup. Exceptions can be caught around the `yield` for rollback.

22. **How do you enforce auth on a whole router without repeating yourself?**
    → `dependencies=[Depends(verify_token)]` on `APIRouter` or `include_router` — dependencies that run for their side effects with no injected return value.

23. **`lifespan` vs `@app.on_event` — and why does this matter?**
    → `on_event` is deprecated; `lifespan` is an `asynccontextmanager` handling startup before `yield` and shutdown after. **This is exactly where your DB engine, HTTP client, and Redis pool should be created** — once per process, not per request.

24. **What are the most common Pydantic v2 changes from v1?**
    → `@validator` → `@field_validator`, plus `@model_validator` for cross-field logic. `class Config` → `model_config = ConfigDict(...)`. `.dict()`/`.json()` → `.model_dump()`/`.model_dump_json()`. `parse_obj` → `model_validate`. Core rewritten in Rust (pydantic-core) — substantially faster. Note FastAPI has been removing v1 internals and `pydantic.v1` now warns.

25. **Why should request and response models be separate classes?**
    → Prevents mass-assignment (client sets `is_admin`) and prevents accidental leakage (hashed password in the response). `response_model` also enforces the output contract and lets FastAPI optimize serialization. A `UserCreate` / `UserUpdate` / `UserPublic` / `UserInDB` split is the expected answer.

26. **`field_validator` vs `model_validator` — give a use case for each.**
    → Field: password length, normalize email to lowercase. Model: "end_date must be after start_date", or "exactly one of A or B must be set." Also know `mode="before"` vs `"after"`.

27. **How does FastAPI generate OpenAPI, and how do you customize it?**
    → From type hints, Pydantic schemas, and route metadata. Customize with `response_model`, `responses={404: {...}}`, `tags`, `summary`, `description`, `openapi_extra`, or by overriding `app.openapi()`. Practical follow-up: how do you hide internal endpoints? (`include_in_schema=False`.)

28. **A client sends a bad payload. What does FastAPI return, and how do you change it?**
    → `422 Unprocessable Entity` with a structured error list. Override with `@app.exception_handler(RequestValidationError)` to match your org's error envelope. Senior point: **a consistent machine-readable error contract across all endpoints matters more than the specific shape** — clients parse it.

29. **How do you design a consistent error-handling strategy across a large API?**
    → Custom exception base class → registered handlers → uniform envelope (`code`, `message`, `details`, `trace_id`). Map domain exceptions to HTTP codes in one place, never in route bodies. Include the correlation ID so support can find the log line.

30. **How does middleware differ from a dependency? When do you use each?**
    → Middleware wraps every request/response at the ASGI layer — logging, timing, correlation IDs, CORS, compression. Dependencies are per-route, typed, and testable. Rule: **cross-cutting and route-agnostic → middleware; anything needing route context or injection → dependency.** Also note pure-ASGI middleware is faster than `BaseHTTPMiddleware`, which has known overhead and streaming edge cases.

31. **How do you version a public API in FastAPI?**
    → Separate `APIRouter`s mounted at `/v1`, `/v2`, sharing a service layer so logic isn't duplicated; or header-based negotiation. Discuss deprecation headers, sunset timelines, and how you avoid forking business logic.

32. **How do you structure a large FastAPI project?**
    → Layered: `api/` (routers, thin), `schemas/` (Pydantic), `models/` (ORM), `services/` (business logic), `repositories/` (data access), `core/` (config, security). Routes should be thin — parse, delegate, serialize. Config via `pydantic-settings` reading env (12-factor). The signal here is that you separate transport from domain.

---

## Section 3 — Databases, ORM & Data Access

33. **You use `AsyncSession` and your queries still block the loop. What's going on?**
    → Almost always: the driver isn't actually async (sync `psycopg2` under the async engine), or lazy loading is triggering I/O outside the async context. Verify the DSN is `postgresql+asyncpg://` (or psycopg 3 async), and eager-load relationships. A "technically async but still slow under load" symptom is the classic report.

34. **What causes `MissingGreenlet` and how do you fix it?**
    → Lazy-loading a relationship outside an active async context — SQLAlchemy's async support uses greenlets to bridge, and touching an unloaded attribute after the session context ends blows up. Fix with `selectinload`/`joinedload`, or `expire_on_commit=False` so objects stay usable after commit.

35. **Where should the async engine and sessionmaker be created?**
    → Once, at app startup in `lifespan`. Creating engines or sessions per request exhausts connections and produces unpredictable performance — this is one of the most common production mistakes.

36. **Explain connection pooling parameters and how you'd size a pool.**
    → `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`, `pool_pre_ping`. Sizing: total connections across all replicas must stay under Postgres `max_connections`. `workers × pool_size × replicas` is the arithmetic to do out loud. With PgBouncer in transaction mode, use `NullPool` in the app.

37. **"APIs scale horizontally, databases scale cautiously." Explain the failure this describes.**
    → Autoscaling your FastAPI pods multiplies pool sizes and saturates the DB connection limit — **the database breaks before the app does.** Fixes: PgBouncer, cap pool sizes, read replicas, and treat connections as a shared global budget rather than a per-pod setting.

38. **What is the N+1 query problem? Show two fixes in SQLAlchemy 2.0.**
    → One query for parents, then one per child access. Fix with `selectinload` (separate IN query, best for collections) or `joinedload` (single JOIN, best for many-to-one). Django equivalent: `prefetch_related` / `select_related`.

39. **Offset pagination vs cursor/keyset pagination — when does offset break?**
    → `OFFSET 100000` makes the DB scan and discard 100k rows, and rows shift under the user between pages. Keyset (`WHERE (created_at, id) < (:last_ts, :last_id) ORDER BY ... LIMIT n`) is O(log n) via index and stable. Say you'd default to cursor for infinite scroll and any large dataset.

40. **How do you find and fix a slow query?**
    → `EXPLAIN (ANALYZE, BUFFERS)`, check for seq scans on large tables, look at `pg_stat_statements` for the worst offenders by total time, add or fix indexes, then re-measure. Discuss index selectivity, composite index column order, covering indexes, and partial indexes.

41. **When does an index hurt?**
    → Write amplification on every INSERT/UPDATE, storage, and planner confusion. Also: low-cardinality columns, and indexes that duplicate a prefix of an existing composite index.

42. **Explain database transaction isolation levels and one anomaly each prevents.**
    → Read Uncommitted (dirty reads), Read Committed (Postgres default — prevents dirty reads, allows non-repeatable reads), Repeatable Read, Serializable. Real-world hook: a read-modify-write on a balance under Read Committed is a lost update — use `SELECT ... FOR UPDATE` or an atomic `UPDATE ... SET x = x - 1`.

43. **How do you handle optimistic vs pessimistic locking in an API?**
    → Optimistic: version column, `UPDATE ... WHERE version = :v`, 0 rows affected → 409 Conflict. Pessimistic: `SELECT FOR UPDATE`, holds a lock, risks contention and deadlocks. Optimistic scales better under low contention; pessimistic is right when conflicts are common and retries are expensive.

44. **How do you manage schema migrations safely with zero downtime?**
    → Alembic, with the expand/contract pattern: add nullable column → backfill in batches → dual-write → switch reads → drop old column, across separate deploys. Never rename or drop in the same release that ships the code change. Mention `CREATE INDEX CONCURRENTLY` and lock timeouts on large tables.

45. **SQL vs NoSQL for a new service — how do you decide?**
    → Access patterns first, not data shape. Relational for transactions, joins, and evolving queries; document stores for denormalized read-heavy access; Redis for ephemeral/cached/session state. The honest senior answer: **Postgres until you have a specific reason not to** — it does JSONB, full-text, and now vectors.

46. **How would you implement soft deletes, and what's the catch?**
    → `deleted_at` column plus a filter everywhere. Catches: every query must remember the filter (use a base repository or query mixin), unique constraints break (use partial unique indexes), and the data still counts as personal data for retention/erasure obligations under DPDP/GDPR.

---

## Section 4 — Authentication, Authorization & Security

47. **Walk through a JWT auth flow end-to-end.**
    → Login → validate credentials → issue short-lived access token (5–15 min) + long-lived refresh token → client sends `Authorization: Bearer` → server verifies signature, expiry, issuer, audience → refresh endpoint rotates. Verify the *algorithm* too, and pin it.

48. **What's the biggest problem with JWTs, and how do you handle it?**
    → They're stateless, so you can't revoke one before expiry. Mitigations: short TTLs, a Redis denylist of revoked JTIs, refresh-token rotation with reuse detection, and a per-user `token_version` that invalidates everything on password change.

49. **Where should the frontend store tokens?**
    → `httpOnly`, `Secure`, `SameSite` cookies for refresh tokens (immune to XSS reads, but needs CSRF protection); access tokens in memory. `localStorage` is XSS-readable — the standard wrong answer.

50. **JWT vs session cookies — defend a choice.**
    → Sessions: revocable instantly, simple, need shared session storage. JWT: stateless, good across services, hard to revoke. Real answer: sessions for first-party web apps, JWT/OAuth for APIs and service-to-service. Don't reach for JWT reflexively.

51. **How do you implement RBAC in FastAPI?**
    → Role or scope claims in the token → a dependency factory `require_role("admin")` returning a `Depends`-able callable → applied per route or per router. For anything richer, move to policy-based checks in the service layer with a permission matrix.

52. **What is BOLA/IDOR, and why is it the #1 API vulnerability?**
    → Broken Object Level Authorization: the user is authenticated but you never check they *own* the object — `GET /orders/123` returns someone else's order. It's #1 on the OWASP API Top 10 because auth middleware doesn't catch it; the check has to live at the data-access layer. Answer: **authorize per object, in the repository or service, never just at the route.**

53. **How do you prevent SQL injection when you need a raw query?**
    → Bound parameters via `text("... WHERE id = :id")` with params, never f-strings. Identifiers (table/column names) can't be parameterized — allow-list them. Note that the ORM protects values, not dynamic structure.

54. **Design rate limiting. Compare the algorithms.**
    → Fixed window (simple, burst at boundaries), sliding window log (accurate, memory-heavy), sliding window counter (good compromise), token bucket (allows bursts, smooth refill), leaky bucket (smooths output). Implement in Redis with a Lua script for atomicity. Return `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After` on 429. **This exact challenge, headers included, appears in senior banks — practice it.**

55. **What is an idempotency key and where do you need one?**
    → Client sends `Idempotency-Key` on POST; server stores key → response, returns the cached result on retry. Essential for payments and any non-idempotent operation over an unreliable network. Discuss the race: two concurrent requests with the same key need a unique constraint or lock, not a check-then-write.

56. **Explain CORS. Why does `allow_origins=["*"]` with credentials fail?**
    → Browser-enforced same-origin policy relaxation via preflight `OPTIONS`. The spec forbids wildcard origin together with `allow_credentials=True` — you must echo specific origins. Also: CORS is not a server-side security control; it protects browsers, not your API.

57. **How do you handle secrets and config?**
    → `pydantic-settings` reading env vars, secrets from Vault/AWS Secrets Manager/Azure Key Vault injected at runtime, never in the image or repo, rotation policy, separate credentials per environment. Never log them — add a redaction filter.

58. **How do you securely handle file uploads?**
    → Validate content type by sniffing magic bytes not the extension or client-supplied MIME, enforce size limits (at the proxy too, not just in app code), generate server-side storage paths to prevent traversal and collisions, store outside the web root or in object storage, scan for malware, and stream to disk rather than buffering in memory.

---

## Section 5 — Performance, Caching & Scaling

59. **Design a caching layer for a read-heavy API.**
    → Cache-aside as default: check Redis → miss → DB → populate with TTL. Key design including tenant/version, TTL with jitter, and explicit invalidation on write. Discuss write-through and write-behind and why cache-aside usually wins on simplicity.

60. **What is a cache stampede and how do you prevent it?**
    → A hot key expires and N concurrent requests all hit the DB simultaneously. Fixes: distributed lock so one request recomputes, probabilistic early expiration, stale-while-revalidate, or TTL jitter so keys don't expire in lockstep. Good senior signal — most candidates miss this.

61. **How do you do HTTP-level caching correctly?**
    → `Cache-Control` (max-age, s-maxage, private/public), `ETag` + `If-None-Match` → 304, `Last-Modified` + `If-Modified-Since`. Cheapest possible win: a 304 costs you almost nothing and saves the client a full payload.

62. **Your p99 latency is 10× your p50. What does that tell you and how do you investigate?**
    → Not a throughput problem — a tail problem. Suspects: GC pauses, connection pool exhaustion (requests queueing for a connection), cold caches, a slow dependency without a timeout, lock contention, or noisy neighbors. Investigate with distributed traces on the slow requests specifically, not aggregate dashboards. **Always talk in percentiles, never averages.**

63. **How do you profile a FastAPI app in production?**
    → `py-spy` (sampling, no code change, safe on prod), timing middleware emitting per-route histograms, distributed tracing to find which span dominates, `tracemalloc`/`memray` for memory. Emphasize measure → change one thing → re-measure.

64. **How do you find a memory leak in a long-running Python service?**
    → `tracemalloc` snapshots diffed over time, `objgraph` for reference chains, `memray` for allocation profiling. Common culprits: unbounded module-level caches/dicts, accumulating task references, and closures holding large objects. Note that steadily rising RSS with flat traffic is the signature.

65. **How do you make an external HTTP call correctly from FastAPI?**
    → A single `httpx.AsyncClient` created in `lifespan` and reused — per-request clients destroy connection pooling and leak sockets. Always set explicit timeouts (connect and read separately), retry with jittered backoff on transient failures only, and never retry non-idempotent operations blindly.

66. **Explain the circuit breaker pattern and why it beats retries alone.**
    → Closed → (failures exceed threshold) → Open (fail fast immediately, don't even try) → Half-Open (probe) → Closed. Retries against a dead dependency amplify load and turn a partial outage into a total one. **Retries without a circuit breaker are how you take down your own recovering service.**

67. **How do you decide between vertical and horizontal scaling — and what makes a service scalable horizontally?**
    → Statelessness is the prerequisite: no in-process session state, no local file dependencies, no in-memory caches assumed shared. Externalize state to Redis/DB/object storage. Then horizontal scaling is a config change rather than a rewrite.

68. **How do you set worker count for a FastAPI deployment?**
    → Each Uvicorn worker is a separate process with its own event loop and pool. Start around `2 × cores` for mixed workloads and tune under real load. In Kubernetes, prefer one worker per container and scale with replicas — it gives cleaner resource limits, autoscaling signals, and rollouts.

69. **How do you handle a slow third-party dependency in a request path?**
    → Timeout aggressively, circuit break, cache aggressively, degrade gracefully (serve stale, or a partial response), and if the operation isn't needed synchronously, move it to a queue and return 202. The framing to use: **decide the user-facing contract first, then pick the mechanism.**

70. **What's the difference between throughput and latency, and when do they trade off?**
    → Batching raises throughput and raises latency. Bigger connection pools raise throughput until the DB becomes the bottleneck, then raise latency. Know that you optimize one at the expense of the other and the business decides which matters.

---

## Section 6 — Testing, Debugging & Observability

71. **How do you test a FastAPI app? What's your layering?**
    → Unit tests on services with dependencies faked, integration tests via `TestClient` (or `httpx.AsyncClient` with `ASGITransport` for async), and a thin layer of contract tests. Use `app.dependency_overrides` to swap DB/auth — this is *the* FastAPI-specific testing answer.

72. **How do you test against a real database without tests polluting each other?**
    → Testcontainers or a dedicated test DB, each test wrapped in a transaction that rolls back, or truncate-between-tests. Factory fixtures (`factory_boy`/`polyfactory`) instead of shared fixtures so tests don't couple. Never share mutable state between tests.

73. **How do you test async code specifically?**
    → `pytest-asyncio` (or `anyio`), async fixtures, and awareness that event-loop scoping between fixtures and tests is the usual source of "works alone, fails in suite."

74. **What do you actually assert about an endpoint?**
    → Status code, response schema, the contract's error cases, authorization boundaries (can user A read user B's object?), and side effects. Testing only the happy path on a 200 is the junior answer.

75. **You're getting intermittent 500s in production that you can't reproduce. Walk through your process.**
    → Correlation IDs to find the failing requests → structured logs filtered to those → stack traces from the error tracker (Sentry) → look for a pattern: specific tenant, payload shape, time of day, pod, or deploy. Suspect: connection pool exhaustion under load, a race, a downstream timeout, or a partially rolled-out deploy. Then reproduce under load, not in isolation. **This is a real senior-bank question — practice narrating it.**

76. **What do you log, and what do you never log?**
    → Structured JSON with correlation/trace ID, user/tenant ID, route, latency, status. Never: passwords, tokens, full PII, card data, or entire request bodies by default. Discuss sampling for high-volume routes and retention policy (which is now a DPDP compliance question, not just cost).

77. **Explain the difference between logs, metrics, and traces.**
    → Logs = discrete events (what happened). Metrics = aggregates over time (how much, how fast — RED: rate, errors, duration). Traces = one request's path across services (where the time went). You need all three; traces are what actually find distributed latency.

78. **How would you implement request tracing across microservices?**
    → OpenTelemetry with W3C `traceparent` propagation, auto-instrumentation for FastAPI/SQLAlchemy/httpx, span attributes for tenant and route, export to Jaeger/Tempo/Datadog. Ensure the trace ID appears in every log line so logs and traces join.

79. **What health checks does a production service need?**
    → Liveness (am I alive — cheap, no dependencies), readiness (can I serve traffic — checks DB/Redis), startup (slow init). Critical nuance: **liveness must not check dependencies**, or a brief DB blip causes Kubernetes to kill every healthy pod, turning a small problem into an outage.

80. **How do you set up CI/CD for a Python backend?**
    → Lint/format (ruff), type check (mypy), tests with coverage gates, build and scan the image, deploy to staging, smoke test, then canary or blue-green to prod with automated rollback on error-rate SLO breach. Migrations run as a separate, backward-compatible step *before* the code deploy.

---

## Section 7 — Deployment, Docker & Operations

81. **Walk through your production Dockerfile for a FastAPI service.**
    → Multi-stage build, slim base, dependencies layer separate from source for cache hits, non-root user, `.dockerignore`, no dev deps, explicit `EXPOSE`, and an entrypoint that doesn't swallow signals (`exec` form). Mention `uv` or pinned lockfiles for reproducible installs.

82. **Gunicorn + UvicornWorker vs plain Uvicorn — which and why?**
    → Gunicorn gives process supervision and graceful restarts; plain `uvicorn --workers` is simpler. Under Kubernetes, the orchestrator already supervises, so single-process containers plus replicas is usually cleaner. Have a position, and give the reason.

83. **How do you achieve zero-downtime deploys?**
    → Rolling update with readiness gates, `preStop` hook plus a grace period so in-flight requests drain, `SIGTERM` handled by the lifespan shutdown, backward-compatible migrations, and health checks that actually reflect readiness. Explain the drain sequence — most candidates skip it.

84. **What happens to in-flight requests when a pod gets SIGTERM?**
    → Kubernetes removes it from endpoints (eventually — there's a propagation race), sends SIGTERM, waits `terminationGracePeriodSeconds`, then SIGKILL. Uvicorn stops accepting new connections and finishes in-flight ones. The race is why you add a `preStop sleep` — that detail is a strong signal.

85. **How do you configure an app across environments?**
    → 12-factor: config from environment, `pydantic-settings` with typed validation and fail-fast on missing required values at startup. No environment `if` branches in code.

86. **How do you set CPU and memory requests/limits for a Python API?**
    → Measure first. Requests from observed steady state, limits with headroom. Key warning: **CPU limits cause throttling that looks exactly like slow code** — a classic misdiagnosis. Memory limits cause OOMKills; watch for restart loops.

87. **How do you handle background workers in Kubernetes?**
    → Separate deployment from the API (different scaling profile, different failure domain), autoscale on queue depth not CPU, graceful shutdown that finishes the current task, idempotent task design, and a dead-letter queue with alerting.

88. **What's your strategy for a service that must serve both an internal admin UI and a public API?**
    → Separate routers and separate auth schemes; ideally separate deployments sharing a service layer, so the admin surface isn't internet-reachable and can scale and be secured independently.

---

## Section 8 — System Design Scenarios
### Where senior offers are won and lost. Practice these out loud with a whiteboard.

For every one: **clarify requirements and scale → sketch the API contract → data model → the happy path → the bottleneck → the failure modes → the trade-off you chose and why.** Do not start drawing boxes before asking about scale.

89. **Design a URL shortener.**
    → Key decisions: ID generation (counter + base62 vs hash vs pre-generated key pool), collision handling, read-heavy access pattern → aggressive caching and CDN, 301 vs 302 (302 preserves analytics), custom aliases, expiry, and analytics as an async write path.

90. **Design a rate limiter that works across many API instances.**
    → Redis as the shared counter, Lua for atomic check-and-increment, algorithm choice justified, degradation policy when Redis is down (fail open or closed — a real business decision you should raise), per-tenant vs per-IP vs per-key, and where it sits (gateway vs app).

91. **Design a real-time notification system for millions of concurrent connections.**
    → WebSocket/SSE tier separated from the API tier, Redis pub/sub or Kafka as the backplane so any node can reach any connection, connection registry, sticky routing or a shared presence store, heartbeats and reconnect with resume tokens, and fanout strategy (per-user channels vs topic). Discuss why one process can't hold a million sockets.

92. **Design a distributed task queue with priorities, retries, and monitoring.**
    → Broker choice (Redis vs RabbitMQ vs SQS vs Kafka) with justification, priority queues or separate queues per class, exponential backoff with jitter, max retries → DLQ, idempotent handlers because delivery is at-least-once, visibility timeouts, and monitoring on queue depth and age of oldest message. Say explicitly: **exactly-once delivery doesn't exist — you get at-least-once plus idempotency.**

93. **Design a multi-tenant SaaS backend. How do you guarantee isolation?**
    → Three models: shared schema + `tenant_id` (cheapest, riskiest), schema-per-tenant, database-per-tenant (strongest isolation, operationally heavy). Enforcement: Postgres row-level security or a repository layer where tenant scoping cannot be forgotten, plus per-tenant rate limits and noisy-neighbor protection. Discuss how you'd migrate a tenant to a dedicated DB as they grow.

94. **Design an event-driven microservice architecture. How do you keep data consistent?**
    → No distributed transactions: use the **transactional outbox** (write state + event in one local transaction, relay publishes) and **saga** with compensating actions for multi-service workflows. Cover idempotent consumers, event versioning/schema registry, ordering guarantees, and why 2PC is usually the wrong answer at scale.

95. **Design a search and filtering system with facets and real-time indexing.**
    → Postgres full-text (`tsvector` + GIN) for moderate scale vs Elasticsearch/OpenSearch when you need relevance tuning and facets at scale. Indexing pipeline via CDC or outbox, eventual consistency window, faceted aggregation, and the trade-off of dual-store consistency.

96. **Design a file upload and processing pipeline for large files.**
    → Presigned URLs so bytes never traverse your API, multipart/resumable upload, metadata record with status state machine, queue for processing, virus scan, progress tracking in Redis, webhook or SSE for completion, and retry/cleanup for orphaned uploads.

97. **Design a payments integration.**
    → Idempotency keys, a state machine for payment status, webhook handling (verify signature, handle out-of-order and duplicate delivery, respond fast and process async), reconciliation job against the provider, and audit trail. Never trust the client to report success.

98. **Design an API gateway layer for a set of internal microservices.**
    → Responsibilities: auth termination, rate limiting, routing, request/response transformation, observability injection. Explicitly discuss what should *not* live there (business logic), and the risk of the gateway becoming a distributed monolith.

99. **You're migrating a Django monolith to services. How do you sequence it?**
    → Strangler fig: put a routing layer in front, extract the highest-value bounded context first, dual-write or CDC during transition, migrate reads then writes, delete the old path only after verification. Address shared-database decoupling — usually the hardest part. **Be ready for this one: your Django + FastAPI background makes it the most likely scenario you'll be handed.**

100. **Design the backend for an LLM-powered feature (chat over documents) — the AI-flavored backend question.**
     → API contract with streaming, async job pattern for ingestion, vector store choice, request-scoped concurrency limits against the provider, token-based rate limiting per tenant, prompt caching, semantic cache with per-tenant keys, circuit breaker plus fallback model, per-request cost attribution, and observability on tokens and latency (TTFT vs total). **This is where your AI experience and backend experience compound — expect it in every AI Engineer loop.**

---

## Bonus A — Django & the Django-vs-FastAPI question

You'll be asked to justify knowing both. Have crisp answers:

- **When would you choose Django over FastAPI?** Full product with admin, auth, ORM, templates; team velocity on CRUD; mature ecosystem. FastAPI for API-first services, async-heavy I/O, ML/LLM serving, and microservices.
- **Django ORM: `select_related` vs `prefetch_related`.** JOIN for FK/one-to-one vs separate query for M2M/reverse FK.
- **What are Django signals and why are they controversial?** Implicit coupling, hard to trace, hard to test — prefer explicit service calls.
- **How does Django handle async now?** ASGI support and async views exist, but the ORM is still sync-first (`sync_to_async` wrappers), so the async story is partial. Django-Ninja gives FastAPI-like ergonomics on Django.
- **Django middleware vs FastAPI middleware.** Different lifecycle and ordering semantics; know both.
- **How do you scale a Django app?** Same fundamentals: caching, query optimization, task queues, read replicas, stateless workers.

---

## Bonus B — The live coding / take-home challenges

Senior banks skew heavily toward these. Build each once before your interviews — they take an hour and they recur constantly:

1. JWT auth dependency with claim extraction, graceful handling of expiry and invalid signatures
2. Redis sliding-window rate limiter as middleware, with correct `X-RateLimit-*` headers
3. Background file processor: async upload → Redis progress → webhook on completion, with retries
4. WebSocket chat with broadcast, presence tracking, and reconnection handling
5. Cursor-based pagination with regex-validated, interdependent query params
6. Transaction-managing DB dependency with automatic rollback and nested transaction support
7. Redis response cache with TTL, tag-based invalidation, and ETag conditional requests
8. Streaming CSV endpoint that transforms chunk-by-chunk without loading the file into memory
9. Circuit breaker for outbound calls with configurable thresholds and exponential-backoff recovery
10. Custom exception handlers producing a consistent error envelope
11. Timing middleware that logs per-request duration and flags slow endpoints
12. LRU cache with GET/PUT endpoints — state the time complexity (O(1) via dict + doubly linked list, or `OrderedDict`)

Also expect classic DSA delivered *as endpoints*: sliding window maximum, min-stack in O(1), two-sum pairs, longest substring without repeating characters, binary search on a rotated array, merge k sorted arrays, trie with insert/search/prefix, cycle detection in a linked list, top-N via priority queue.

---

## How to prepare, given your background

Your six years and Django experience mean **nobody will doubt you can build a CRUD API.** They'll probe two things instead: whether your async understanding is real or cargo-culted, and whether you can own a service end-to-end in production.

**Highest leverage, in order:**
1. **Section 1 until it's reflexive.** Be able to explain the event loop in 60 seconds with the restaurant metaphor, then immediately give the four blocking categories and their fixes. This one block of knowledge is what got that eight-year candidate rejected.
2. **Build the sliding-window rate limiter and the circuit breaker this week.** They appear in nearly every senior bank and you'll speak about them completely differently once you've written them.
3. **Practice Section 8 out loud, on a whiteboard, timed to 40 minutes.** Q99 (Django monolith → services) and Q100 (LLM backend) are the two most likely to be handed to you specifically.
4. **Bring numbers.** "We ran 4 replicas, pool_size 10, p95 at 180ms, and the fix took p99 from 4s to 300ms by moving the sync Boto3 call out of the async route" is worth more than any definition in this document.

**One warm-up drill that pays for itself:** take the worst-performing endpoint you've ever shipped, and rehearse the story — symptom, hypothesis, tooling, root cause, fix, measured result. Some version of that story fits at least six of the questions here.

---

*Version-specific details (FastAPI 0.13x, Pydantic 2.13.x, Starlette 1.0, SQLAlchemy 2.0) were current as of 23 July 2026. Re-check anything version-pinned before you interview.*

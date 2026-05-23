# Production Staging Runbook

Phase 7 prepares staging for the backend and sync API. Markdown remains the product memory source of truth. PostgreSQL stores users, metadata, audit/action rows, sync versions, key wraps, and recovery wraps only; synchronized memory file content must stay encrypted before it reaches server storage.

## Services

- Backend API: FastAPI on container port `8000`, behind Nginx.
- HTTPS proxy: Nginx terminates TLS and proxies HTTP/WebSocket traffic to the backend.
- PostgreSQL: metadata database only.
- Redis: Celery broker/result backend and rate-limit counter store.
- Object storage: S3-compatible storage for encrypted sync blobs.
- Worker: Celery worker for background jobs.

Port `8069` is intentionally unused. The staging compose file maps only `8080:80` and `8443:443` by default.

## ari.flusscreative.com Plesk Deployment

`ari.flusscreative.com` is the first public staging domain. It is managed by Plesk on `51.195.44.82`; Plesk terminates HTTPS and serves the public domain.

Use this profile when deploying behind Plesk:

- Compose file: `infra/docker/docker-compose.plesk.yml`
- Debian 10 / docker-compose v1 fallback: `infra/docker/docker-compose.plesk.v1.yml`
- Environment example: `infra/docker/.env.plesk.example`
- Plesk nginx snippet: `infra/docker/nginx/plesk-additional-directives.conf`

This profile binds the backend to `127.0.0.1:18000` only. Do not publish backend, PostgreSQL, or Redis directly to the Internet.

From `infra/docker` on the server:

```sh
cp .env.plesk.example .env.plesk
```

Edit `.env.plesk` and replace every placeholder. Then start the stack:

```sh
docker compose --env-file .env.plesk -f docker-compose.plesk.yml up -d --build
docker compose --env-file .env.plesk -f docker-compose.plesk.yml exec backend alembic upgrade head
curl http://127.0.0.1:18000/ready
```

On Debian 10 servers with legacy `docker-compose 1.x`, use:

```sh
set -a
. ./.env.plesk
set +a
docker-compose -p ari -f docker-compose.plesk.v1.yml up -d --build
docker-compose -p ari -f docker-compose.plesk.v1.yml exec backend alembic upgrade head
curl http://127.0.0.1:18000/ready
```

In Plesk, open:

```text
ari.flusscreative.com > Apache & nginx Settings > Additional nginx directives
```

Paste the contents of `infra/docker/nginx/plesk-additional-directives.conf`, then apply. After Plesk reloads nginx:

```sh
curl https://ari.flusscreative.com/health
curl https://ari.flusscreative.com/ready
```

Expected result: Plesk continues handling HTTPS, while `/health`, `/ready`, `/api/v1/*`, and `/ws/agent` are proxied to the backend.

For this Plesk profile, encrypted sync blobs use the `syncdata` Docker volume. Move to S3-compatible object storage before production if staging data needs host-independent object durability.

## Required Files

- `infra/docker/docker-compose.staging.yml`
- `infra/docker/.env.staging`
- `infra/docker/certs/fullchain.pem`
- `infra/docker/certs/privkey.pem`

Create `infra/docker/.env.staging` from `infra/docker/.env.staging.example` and replace every placeholder with generated staging values. Do not commit `.env.staging`, TLS private keys, or backup dumps.

## First Build

From `infra/docker`:

```sh
cp .env.staging.example .env.staging
```

Edit `.env.staging`, then install certificates into `infra/docker/certs`.

For local staging smoke tests, use a local certificate pair named exactly:

- `fullchain.pem`
- `privkey.pem`

Start staging:

```sh
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d --build
```

Apply migrations:

```sh
docker compose --env-file .env.staging -f docker-compose.staging.yml exec backend alembic upgrade head
```

Check health:

```sh
curl -k https://127.0.0.1:8443/health
curl -k https://127.0.0.1:8443/ready
```

`/ready` must report `database` and `redis` as `ok`.

## HTTPS

Nginx redirects HTTP to HTTPS and sets baseline security headers:

- `Strict-Transport-Security`
- `X-Content-Type-Options`
- `X-Frame-Options`
- `Referrer-Policy`

For a public staging host, replace the local port mapping with `80:80` and `443:443` only after DNS and certificates are ready.

## PostgreSQL Backups

Run a manual backup:

```sh
docker compose --env-file .env.staging -f docker-compose.staging.yml --profile ops run --rm backup
```

The backup lands in `infra/docker/backups` as a custom-format `.dump` file plus a `.sha256` checksum. Store copies outside the host after every backup.

Suggested schedule for staging:

- Daily backup.
- Keep 7 daily backups.
- Keep 4 weekly backups.
- Test restore after any migration that changes sync, auth, key-wrap, or audit tables.

## Restore Drill

Choose a dump from `infra/docker/backups`, then run:

```sh
docker compose --env-file .env.staging -f docker-compose.staging.yml run --rm \
  --entrypoint /scripts/restore-postgres.sh \
  -e BACKUP_FILE=/backups/ai-assistant-ai_assistant-YYYYMMDDTHHMMSSZ.dump \
  backup
```

After restore:

```sh
docker compose --env-file .env.staging -f docker-compose.staging.yml exec backend alembic upgrade head
curl -k https://127.0.0.1:8443/ready
```

A restore is accepted only when `/ready` is `ok` and authenticated sync metadata can be listed for a known test workspace.

## Object Storage

Staging uses MinIO through the same S3-style settings the backend expects:

- `SYNC_STORAGE_BACKEND=s3`
- `S3_ENDPOINT_URL=http://minio:9000`
- `S3_BUCKET`
- `S3_REGION`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`

Only encrypted sync blobs are written to object storage. The object key uses workspace/file/version/checksum metadata, not memory text. The backend does not decrypt synced content.

For managed production object storage, set the provider endpoint and credentials in the environment and keep bucket access private.

## Logs And Metrics

Baseline logs are container stdout/stderr:

```sh
docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f backend worker nginx
```

Minimum staging metrics to watch:

- Backend 5xx responses.
- Nginx 4xx/5xx responses.
- `/ready` database and Redis checks.
- PostgreSQL storage growth.
- Object storage object count and storage growth.
- Redis memory and evictions.
- Backup age and latest restore-drill date.

## Rate Limiting

Rate limiting is enabled in staging by default through Redis-backed fixed windows:

- `RATE_LIMIT_ENABLED=true`
- `RATE_LIMIT_REQUESTS=120`
- `RATE_LIMIT_WINDOW_SECONDS=60`

`/health` and `/ready` are exempt. Rate-limit responses return `429` plus `Retry-After` and `X-RateLimit-*` headers.

## Security Checklist

- `SECRET_KEY` is not `change-me-in-production`.
- `.env.staging`, `certs/*.pem`, and `backups/*` are ignored and not committed.
- `DEBUG=false`; OpenAPI docs are disabled.
- `ALLOWED_ORIGINS` contains only the staging frontend/app origins.
- Public host does not expose Postgres, Redis, MinIO, or backend port `8000` directly.
- Port `8069` is not used.
- HTTPS is enabled before using real accounts.
- Sync content uploads require encryption headers.
- PostgreSQL contains no plaintext memory content.
- Object storage bucket is private.
- Backup restore has been tested after setup.

## Deployment Notes

Phase 7 is backend staging only. Mobile E2EE completion, automatic summary generation, and recovery UX remain future work and do not block staging as long as production sync content remains client-encrypted.

# Production deployment

This directory contains the production stack. It runs the API and both RQ
workers from the published `fossasia/veditor` image, while PostgreSQL and Redis
keep their data in named Docker volumes.

## Provision a host

1. Install Docker Engine and the Compose plugin.
2. Create a deployment directory and copy `docker-compose.yml` and `env.sample`
   into it as `docker-compose.yml` and `.env`.
3. Set a strong database password and `SESSION_SECRET` (at least 32 bytes).
4. Log in to Docker Hub if the repository is private.
5. Start the stack:

   ```bash
   docker compose pull
   docker compose up -d
   docker compose ps
   ```

The API waits for PostgreSQL and Redis, runs `alembic upgrade head` once, and
then starts Uvicorn. Workers wait for the same services but never run
migrations. Watchtower checks the `latest` image every five minutes and only
updates containers carrying its enable label. Worker restarts allow up to 120
seconds for an active job to stop cleanly.

## Reverse proxy and HTTPS

Keep port 8000 private to the host or firewall and put Nginx, Caddy, or another
TLS reverse proxy in front of it. Proxy HTTPS traffic to
`http://127.0.0.1:8000`, forward the `Host` and `X-Forwarded-Proto` headers,
and configure `BASE_URL` to the public HTTPS URL. Obtain and renew the
certificate in the proxy rather than in the application container.

## Operations

Check service logs with `docker compose logs -f api` or
`docker compose logs -f worker-heavy`. Back up PostgreSQL before planned
changes, and do not remove the named volumes: they contain the database,
Redis queue data, uploaded recordings, and generated video files.

Every successful deployment workflow publishes a new `latest` image. To apply
it immediately instead of waiting for Watchtower's five-minute poll:

```bash
docker compose pull
docker compose up -d
```

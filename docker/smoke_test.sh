#!/usr/bin/env bash
# Smoke test of the Docker image (spec 005), used by CI and runnable locally:
#   docker build -t ptf:local . && docker/smoke_test.sh ptf:local
#   with the asia image too: ASIA_IMAGE=ptf:asia docker/smoke_test.sh ptf:local
# Checks: no data or secrets baked in, non-root user, the CLI works, and the app becomes
# healthy without any warehouse (it shows its "no data yet" start page).
set -euo pipefail

IMAGE="${1:-ptf:local}"
NAME="ptf-smoke-$$"
PORT="${SMOKE_PORT:-18050}"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "1. no data, no .env, no uv in the image"
docker run --rm "$IMAGE" sh -c 'test ! -e /app/data && test ! -e /app/.env && ! command -v uv'

echo "2. runs as the unprivileged user 'ptf'"
test "$(docker run --rm "$IMAGE" whoami)" = "ptf"

echo "3. the pipeline command line answers"
docker run --rm "$IMAGE" ptf --help >/dev/null

echo "4. the app becomes healthy without a warehouse"
docker run -d --name "$NAME" -p "127.0.0.1:${PORT}:8050" "$IMAGE" >/dev/null
for _ in $(seq 1 30); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$NAME")"
    [ "$status" = "healthy" ] && break
    sleep 3
done
if [ "$status" != "healthy" ]; then
    docker logs "$NAME"
    echo "app container is '$status', expected 'healthy'" >&2
    exit 1
fi
curl -fsS "http://127.0.0.1:${PORT}/_dash-layout" | grep -q '"no-data"'

if [ -n "${ASIA_IMAGE:-}" ]; then
    echo "5. asia image: AKShare importable, step dce known, root file system read-only"
    docker run --rm "$ASIA_IMAGE" python -c "import akshare"
    docker run --rm "$ASIA_IMAGE" ptf --help | grep -q "dce"
    if docker run --rm --read-only --tmpfs /tmp "$ASIA_IMAGE" sh -c 'touch /app/x' 2>/dev/null; then
        echo "asia container could write outside the mounted folder" >&2
        exit 1
    fi
fi

echo "smoke test passed: $IMAGE"

#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENGINE=${CONTAINER_ENGINE:-podman}
IMAGE=${TEST_IMAGE:-tge-rdn-tests}

"$ENGINE" build -f "$ROOT_DIR/Containerfile.test" -t "$IMAGE" "$ROOT_DIR"
"$ENGINE" run --rm -v "$ROOT_DIR:/workspace:Z" -w /workspace "$IMAGE" "$@"

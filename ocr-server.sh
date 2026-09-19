#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="local-paddleocr:3.6.0"
DAEMON_NAME="ocr-daemon"

usage() {
    cat <<EOF
Usage:
  $(basename "$0") start OUTPUT_DIR
  $(basename "$0") stop
  $(basename "$0") status

Runs a long-lived OCR container with all models loaded once in memory.
'ocr.sh' automatically uses the daemon (fast path) when it is running and
its OUTPUT_DIR matches, and falls back to a one-shot container otherwise.
EOF
}

cmd_start() {
    if [[ $# -ne 1 ]]; then
        usage >&2
        exit 1
    fi

    mkdir -p "$1"
    OUTPUT_ABS="$(realpath "$1")"

    if [[ "$(docker inspect -f '{{.State.Running}}' "$DAEMON_NAME" 2>/dev/null || true)" == "true" ]]; then
        echo "ERROR: $DAEMON_NAME is already running. Stop it first: $(basename "$0") stop" >&2
        exit 1
    fi

    docker rm -f "$DAEMON_NAME" >/dev/null 2>&1 || true

    echo "Starting $DAEMON_NAME (output: $OUTPUT_ABS)..."

    docker run -d --rm \
        --name "$DAEMON_NAME" \
        --gpus all \
        --network none \
        --user "$(id -u):$(id -g)" \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        --read-only \
        --tmpfs /tmp:rw,noexec,nosuid,size=1g,mode=1777 \
        --tmpfs /run/ocr:rw,noexec,nosuid,size=16m,mode=1777 \
        --pids-limit 256 \
        -v "$PROJECT_DIR/models:/models:ro" \
        -v "$PROJECT_DIR/cache:/cache:rw" \
        -v "$OUTPUT_ABS:/output:rw" \
        --label "ocr.output_dir=$OUTPUT_ABS" \
        "$IMAGE" serve

    echo "Started. Tail logs with: docker logs -f $DAEMON_NAME"
}

cmd_stop() {
    if docker stop "$DAEMON_NAME" >/dev/null 2>&1; then
        echo "Stopped $DAEMON_NAME."
    else
        echo "$DAEMON_NAME is not running."
    fi
}

cmd_status() {
    if [[ "$(docker inspect -f '{{.State.Running}}' "$DAEMON_NAME" 2>/dev/null || true)" == "true" ]]; then
        OUTPUT_DIR="$(docker inspect -f '{{ index .Config.Labels "ocr.output_dir" }}' "$DAEMON_NAME")"
        echo "$DAEMON_NAME is running. Output: $OUTPUT_DIR"
    else
        echo "$DAEMON_NAME is not running."
    fi
}

if [[ $# -lt 1 ]]; then
    usage >&2
    exit 1
fi

SUBCOMMAND="$1"
shift

case "$SUBCOMMAND" in
    start)
        cmd_start "$@"
        ;;
    stop)
        cmd_stop "$@"
        ;;
    status)
        cmd_status "$@"
        ;;
    -h|--help)
        usage
        ;;
    *)
        echo "Unknown command: $SUBCOMMAND" >&2
        usage >&2
        exit 1
        ;;
esac

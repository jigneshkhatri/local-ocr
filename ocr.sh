#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="local-paddleocr:3.6.0"
DAEMON_NAME="ocr-daemon"

usage() {
    cat <<EOF
Usage:
  $(basename "$0") [OPTIONS] INPUT OUTPUT

Examples:
  $(basename "$0") report.pdf output/
  $(basename "$0") Samples/Input Samples/Output
  $(basename "$0") --recursive Samples/Input Samples/Output

Options:
  --recursive       Recursively process PDFs under INPUT
  -h, --help        Show this help
EOF
}

RECURSIVE=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --recursive)
            RECURSIVE=(--recursive)
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

if [[ $# -ne 2 ]]; then
    usage >&2
    exit 1
fi

INPUT="$1"
OUTPUT="$2"

if [[ ! -e "$INPUT" ]]; then
    echo "ERROR: Input does not exist: $INPUT" >&2
    exit 1
fi

mkdir -p "$OUTPUT"

INPUT_ABS="$(realpath "$INPUT")"
OUTPUT_ABS="$(realpath "$OUTPUT")"

# ------------------------------------------------------------
# Fast path: if a long-lived daemon (started via ocr-server.sh) is
# running with a matching OUTPUT_ABS, stream each PDF to it over
# `docker exec` instead of paying a full model-reload cost via
# `docker run`.
# ------------------------------------------------------------

DAEMON_RUNNING="$(docker inspect -f '{{.State.Running}}' "$DAEMON_NAME" 2>/dev/null || true)"

if [[ "$DAEMON_RUNNING" == "true" ]]; then
    DAEMON_OUTPUT="$(docker inspect -f '{{ index .Config.Labels "ocr.output_dir" }}' "$DAEMON_NAME" 2>/dev/null || true)"
else
    DAEMON_OUTPUT=""
fi

if [[ "$DAEMON_RUNNING" == "true" && "$DAEMON_OUTPUT" == "$OUTPUT_ABS" ]]; then
    echo "LocalOCR (daemon)"
    echo "-----------------"
    echo "Container: $DAEMON_NAME"
    echo "Input:     $INPUT_ABS"
    echo "Output:    $OUTPUT_ABS"
    echo

    PDFS=()

    if [[ -f "$INPUT_ABS" ]]; then
        if [[ "${INPUT_ABS,,}" != *.pdf ]]; then
            echo "ERROR: Input file is not a PDF: $INPUT_ABS" >&2
            exit 1
        fi
        PDFS=("$INPUT_ABS")
    else
        if [[ ${#RECURSIVE[@]} -gt 0 ]]; then
            while IFS= read -r -d '' f; do PDFS+=("$f"); done \
                < <(find "$INPUT_ABS" -type f -iname '*.pdf' -print0 | sort -z)
        else
            while IFS= read -r -d '' f; do PDFS+=("$f"); done \
                < <(find "$INPUT_ABS" -maxdepth 1 -type f -iname '*.pdf' -print0 | sort -z)
        fi
    fi

    if [[ ${#PDFS[@]} -eq 0 ]]; then
        echo "No PDF files found."
        exit 0
    fi

    echo "Found ${#PDFS[@]} PDF(s)."

    FAILED=0

    for pdf in "${PDFS[@]}"; do
        echo
        echo "Processing: $pdf"
        if ! docker exec -i "$DAEMON_NAME" python /app/client.py --filename "$(basename "$pdf")" < "$pdf"; then
            FAILED=1
        fi
    done

    echo
    echo "Processing complete."

    exit "$FAILED"
fi

# ------------------------------------------------------------
# Determine how to mount the input.
#
# A single PDF is mounted as:
#
#   /data/<filename>.pdf
#
# A directory is mounted as:
#
#   /data
# ------------------------------------------------------------

if [[ -f "$INPUT_ABS" ]]; then

    INPUT_DIR="$(dirname "$INPUT_ABS")"
    INPUT_FILE="$(basename "$INPUT_ABS")"

    CONTAINER_INPUT="/data/$INPUT_FILE"

    INPUT_MOUNT="$INPUT_DIR:/data:ro"

else

    CONTAINER_INPUT="/data"

    INPUT_MOUNT="$INPUT_ABS:/data:ro"

fi

echo "LocalOCR"
echo "--------"
echo "Image:  $IMAGE"
echo "Input:  $INPUT_ABS"
echo "Output: $OUTPUT_ABS"

if [[ -f "$INPUT_ABS" ]]; then
    echo "Mode:   single PDF"
else
    echo "Mode:   directory"
fi

echo

docker run --rm \
    --gpus all \
    --network none \
    --user "$(id -u):$(id -g)" \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    -v "$PROJECT_DIR/models:/models:ro" \
    -v "$INPUT_MOUNT" \
    -v "$OUTPUT_ABS:/output:rw" \
    -v "$PROJECT_DIR/cache:/cache:rw" \
    "$IMAGE" \
    --input "$CONTAINER_INPUT" \
    --output /output \
    "${RECURSIVE[@]}"
#!/bin/sh
set -e

if [ "$1" = "serve" ]; then
    shift
    exec python /app/server.py "$@"
else
    exec python /app/ocr.py "$@"
fi

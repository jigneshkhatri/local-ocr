import argparse
import json
import socket
import sys
from pathlib import Path


SOCKET_PATH = "/run/ocr/ocr.sock"


def recv_line(conn: socket.socket) -> str:
    chunks = []

    while True:
        chunk = conn.recv(1)

        if not chunk:
            raise ConnectionError("server closed connection early")

        if chunk == b"\n":
            break

        chunks.append(chunk)

    return b"".join(chunks).decode("utf-8")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send one PDF (via stdin) to the OCR daemon."
    )

    parser.add_argument(
        "--filename",
        required=True,
        help="Original filename (used to name the output subdirectory).",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    filename = Path(args.filename).name
    data = sys.stdin.buffer.read()

    if not data:
        print("ERROR: no PDF data received on stdin.", file=sys.stderr)
        return 1

    header = json.dumps({"filename": filename, "size": len(data)}) + "\n"

    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(SOCKET_PATH)
    except OSError as exc:
        print(f"ERROR: could not connect to OCR daemon: {exc}", file=sys.stderr)
        return 2

    try:
        conn.sendall(header.encode("utf-8"))
        conn.sendall(data)

        response = json.loads(recv_line(conn))
    finally:
        conn.close()

    if response.get("ok"):
        print(f"  Done: {filename}")
        return 0

    print(f"  ERROR processing {filename}: {response.get('error', 'unknown error')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

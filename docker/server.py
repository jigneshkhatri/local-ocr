import json
import shutil
import socket
import sys
import traceback
import uuid
from pathlib import Path, PurePosixPath

from pipeline import create_pipeline, process_pdf


SOCKET_PATH = Path("/run/ocr/ocr.sock")
OUTPUT_DIR = Path("/output")
SCRATCH_DIR = Path("/tmp")


def resolve_output_dir(subdir: str) -> Path:
    subdir = subdir or ""

    if PurePosixPath(subdir).is_absolute():
        raise ValueError("output_subdir must be relative")

    candidate = (OUTPUT_DIR / subdir).resolve()

    if candidate != OUTPUT_DIR and OUTPUT_DIR not in candidate.parents:
        raise ValueError("output_subdir escapes the output root")

    return candidate


def recv_exact(conn: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n

    while remaining > 0:
        chunk = conn.recv(min(remaining, 1 << 20))

        if not chunk:
            raise ConnectionError("client closed connection early")

        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def recv_line(conn: socket.socket) -> str:
    chunks = []

    while True:
        chunk = conn.recv(1)

        if not chunk:
            raise ConnectionError("client closed connection early")

        if chunk == b"\n":
            break

        chunks.append(chunk)

    return b"".join(chunks).decode("utf-8")


def handle(conn: socket.socket, pipeline):
    header = json.loads(recv_line(conn))

    filename = Path(header["filename"]).name
    size = int(header["size"])

    data = recv_exact(conn, size)

    if not filename.lower().endswith(".pdf"):
        conn.sendall(
            (json.dumps({"ok": False, "error": "not a PDF"}) + "\n").encode("utf-8")
        )
        return

    try:
        output_dir = resolve_output_dir(header.get("output_subdir", ""))
    except ValueError as exc:
        conn.sendall(
            (json.dumps({"ok": False, "error": str(exc)}) + "\n").encode("utf-8")
        )
        return

    scratch_dir = SCRATCH_DIR / uuid.uuid4().hex
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_path = scratch_dir / filename

    try:
        scratch_path.write_bytes(data)

        ok = process_pdf(pipeline, scratch_path, output_dir)

        conn.sendall(
            (json.dumps({"ok": ok}) + "\n").encode("utf-8")
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def main():
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    pipeline = create_pipeline()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(SOCKET_PATH))
    sock.listen(8)

    print(f"Ready. Listening on {SOCKET_PATH}")

    while True:
        conn, _ = sock.accept()

        try:
            handle(conn, pipeline)
        except Exception:
            traceback.print_exc()
        finally:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())

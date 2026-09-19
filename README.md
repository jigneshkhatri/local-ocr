# LocalOCR

Local, GPU-accelerated PDF OCR and document-structure extraction using
PaddleOCR 3.6.0 (PP-StructureV3), running fully offline in a hardened
Docker container.

## What it does

LocalOCR takes a PDF (or a directory of PDFs) and produces structured
**JSON** and **Markdown** for each page: text, reading order, tables,
formulas and layout regions.

Pipeline stage-by-stage:

```
PDF -> document orientation classification -> document unwarping
    -> layout/region detection -> OCR detection -> OCR recognition
    -> table classification/structure -> formula recognition
    -> JSON + Markdown
```

It is meant to be the OCR/document-understanding stage of a larger
pipeline (e.g. PDF -> LocalOCR -> chunking -> embeddings -> vector DB),
and is deliberately independent of everything downstream of that.

## How it does it — two run modes

Every model load is expensive (13 models, tens of seconds). There are two
ways to run LocalOCR, trading that cost off against how many files you're
processing:

| Mode | Command | Model load cost | Use for |
|---|---|---|---|
| **One-shot** | `./ocr.sh` | Once per invocation (container starts, loads models, processes, exits) | A single file or occasional batches |
| **Daemon** | `./ocr-server.sh start` + `./ocr.sh` | Once total, kept resident until stopped | A pipeline feeding files in one at a time over time |

**One-shot mode** runs `docker run --rm`: a fresh container, fresh model
load, processes everything under `--input`, then exits. Simple, but every
invocation pays the full model-load cost again.

**Daemon mode** runs one long-lived container (`docker run -d`) whose
entrypoint loads all 13 models once and then listens on a Unix domain
socket *inside the container* (`/run/ocr/ocr.sock`) — no TCP port, no
network namespace involved. Each file is handed to it by streaming the raw
PDF bytes through `docker exec -i <container> client.py < file.pdf`; the
client is a tiny process with no ML imports, so it starts in milliseconds
and reuses whatever the daemon already has loaded in memory. `ocr.sh`
detects automatically whether a matching daemon is running and uses it;
otherwise it transparently falls back to one-shot mode. Nothing about
existing one-shot usage changes.

Because the daemon never needs a bind-mounted input directory (input
arrives purely as a byte stream over `docker exec`), it actually has a
*smaller* filesystem surface than one-shot mode — see
[Security model](#security-model).

## Project layout

```
LocalOCR/
├── ocr.sh              # day-to-day CLI: daemon fast path, one-shot fallback
├── ocr-server.sh        # start/stop/status for the daemon container
├── docker/
│   ├── Dockerfile
│   ├── entrypoint.sh     # dispatches `serve` (daemon) vs one-shot CLI
│   ├── pipeline.py       # shared: model loading, PDF discovery, processing
│   ├── ocr.py            # one-shot CLI entrypoint
│   ├── server.py         # daemon: loads models once, serves over Unix socket
│   ├── client.py         # fast client used by ocr.sh in daemon mode
│   └── patch_doc_preprocessor.py  # build-time PaddleX config patch
├── models/               # PaddleOCR/PaddleX model weights (not in Git)
├── cache/                # container HOME (Paddle/HF/etc. runtime cache, not in Git)
└── Samples/
    ├── Input/
    └── Output/
```

`models/` and `cache/` hold large binaries and machine-specific runtime
state — see `.gitignore`, they are not committed.

## Requirements

- Docker with the NVIDIA Container Toolkit (`--gpus all` support)
- An NVIDIA GPU with enough VRAM for 13 concurrently-loaded models
  (a modern 8GB+ desktop/workstation GPU is enough; CUDA/Paddle
  compatibility should be re-checked if you change GPU or base image)
- `git` and, for the model download step, Python 3 with `pip`

## Setup

1. Clone the repo and fetch the models (one-time, requires internet —
   see [Downloading the models](#downloading-the-models) below):

   ```bash
   git clone <this-repo-url> LocalOCR
   cd LocalOCR
   ```

2. Build the image:

   ```bash
   docker build -t local-paddleocr:3.6.0 ./docker
   ```

   The build patches PaddleX's installed `doc_preprocessor` config so the
   nested orientation/unwarping models resolve to local paths instead of
   attempting a download at `predict()` time (see
   [PaddleX DocPreprocessor fix](#paddlex-docpreprocessor-fix)). The build
   log should report it found and patched that configuration — if it
   reports no configuration found, stop and investigate the installed
   PaddleX version rather than enabling runtime networking.

3. Verify GPU access:

   ```bash
   docker run --rm --gpus all --entrypoint bash local-paddleocr:3.6.0 -c "nvidia-smi"
   ```

4. Make the scripts executable (already done if you cloned with
   permissions intact):

   ```bash
   chmod +x ocr.sh ocr-server.sh
   ```

## Downloading the models

`models/` and `cache/` are gitignored — they hold large binaries and
machine-generated runtime state, not source code, so they aren't part of
the repo.

**`cache/`** needs no setup: it's the container's `HOME`, empty at first,
and gets populated automatically the first time you run the container.
Just make sure the directory exists:

```bash
mkdir -p cache
```

**`models/`** must be populated before the first run — this is the one
step that needs internet access, done once, outside the container. All 13
models are published on Hugging Face under the `PaddlePaddle` org, one
repo per model, with names matching the directories listed under
[Models](#models) below. Download them all with:

```bash
pip install -U huggingface_hub

mkdir -p models
for name in \
    PP-DocBlockLayout PP-DocLayout_plus-L PP-FormulaNet_plus-L \
    PP-LCNet_x1_0_doc_ori PP-LCNet_x1_0_table_cls PP-LCNet_x1_0_textline_ori \
    PP-OCRv5_server_det PP-OCRv5_server_rec \
    RT-DETR-L_wired_table_cell_det RT-DETR-L_wireless_table_cell_det \
    SLANet_plus SLANeXt_wired UVDoc; do
    hf download "PaddlePaddle/$name" --local-dir "models/$name"
done
```

(`huggingface-cli` was the old command name — recent `huggingface_hub`
versions renamed it to `hf`, no `[cli]` extra needed. If `hf` isn't found,
upgrade with `pip install -U huggingface_hub`.)

Each resulting `models/<name>/` should contain `config.json`,
`inference.json`, `inference.pdiparams` and `inference.yml`. Once this is
done, everything else — build and every `ocr.sh`/`ocr-server.sh` run —
is fully offline (`--network none`); the models are never fetched again.

## Running it

### One-shot (no setup, simplest)

```bash
./ocr.sh report.pdf output/                    # single PDF
./ocr.sh Samples/Input Samples/Output           # directory
./ocr.sh --recursive Samples/Input Samples/Output  # directory, recursive
```

### Daemon (for pipelines processing many files over time)

```bash
./ocr-server.sh start Samples/Output   # starts once, models load, stays resident
./ocr.sh report1.pdf Samples/Output    # fast — reuses the loaded models
./ocr.sh report2.pdf Samples/Output    # fast — reuses the loaded models
./ocr-server.sh status
./ocr-server.sh stop                   # when the pipeline is idle
```

The daemon's output directory is fixed at start time (`docker exec`
can't add new mounts to a running container). `ocr.sh` only takes the
fast path when the `OUTPUT` you pass it matches the directory the daemon
was started with; otherwise it falls back to one-shot mode automatically.
Input needs no matching mount — any host path works, since it's streamed
in rather than bind-mounted.

### `ocr.sh` reference

```
ocr.sh [OPTIONS] INPUT OUTPUT
```

| Arg/Option | Meaning |
|---|---|
| `INPUT` | A single PDF file, or a directory containing PDFs. Required. |
| `OUTPUT` | Directory to write results into; created if it doesn't exist. Required. |
| `--recursive` | When `INPUT` is a directory, also search subdirectories (default: only PDFs directly inside `INPUT`). Ignored when `INPUT` is a single file. |
| `-h`, `--help` | Print usage and exit. |

Whether a given call uses the daemon or one-shot mode is decided
automatically (see [above](#how-it-does-it--two-run-modes)) — there's no
flag for it.

### `ocr-server.sh` reference

```
ocr-server.sh start OUTPUT_DIR
ocr-server.sh stop
ocr-server.sh status
```

| Subcommand | Meaning |
|---|---|
| `start OUTPUT_DIR` | Starts the daemon container, loads all models, and fixes its writable output mount to `OUTPUT_DIR`. Fails if a daemon is already running. |
| `stop` | Stops the daemon container (it runs with `--rm`, so it's removed automatically). |
| `status` | Prints whether the daemon is running and, if so, which `OUTPUT_DIR` it was started with. |
| `-h`, `--help` | Print usage and exit. |

Only `ocr.sh` calls whose `OUTPUT` matches the daemon's `OUTPUT_DIR`
(compared as absolute paths) take the fast path — everything else falls
back to one-shot mode.

### Output

For `report.pdf`, output lands in a subdirectory named after the file:

```
output/
└── report/
    ├── report_0.md
    ├── report_0_res.json
    └── imgs/
```

JSON is for machine processing; Markdown is for inspection or downstream
chunking/LLM workflows.

## Security model

Both modes run fully offline and locked down. Daemon mode adds further
hardening since it stays alive for longer:

| Flag | One-shot | Daemon | Purpose |
|---|---|---|---|
| `--network none` | yes | yes | No internet access, period — also fails loudly instead of silently downloading a missing model |
| `--cap-drop ALL` | yes | yes | No Linux capabilities |
| `--security-opt no-new-privileges:true` | yes | yes | Blocks privilege escalation |
| `--user "$(id -u):$(id -g)"` | yes | yes | Runs as the host user, not root |
| `models:ro` | yes | yes | Models mounted read-only |
| `--read-only` (rootfs) | no | yes | Container's own filesystem can't be written to at all |
| `--tmpfs /tmp`, `--tmpfs /run/ocr` | — | yes (`noexec,nosuid`, size-capped) | Only writable space: OCR scratch files and the Unix socket |
| `--pids-limit 256` | no | yes | Caps process/thread count |
| input bind mount | `/data:ro` | **none** | Daemon never gets filesystem access to host input directories at all — input is streamed bytes only |
| `/output:rw`, `/cache:rw` | yes | yes | Only place either mode can write |

## Models

All 13 models are expected under `models/<name>` and mounted read-only at
`/models` inside the container:

- **Preprocessing**: `PP-LCNet_x1_0_doc_ori` (orientation),
  `UVDoc` (unwarping) — both intentionally always enabled
- **Layout**: `PP-DocLayout_plus-L`, `PP-DocBlockLayout`
- **OCR**: `PP-OCRv5_server_det`, `PP-OCRv5_server_rec`,
  `PP-LCNet_x1_0_textline_ori`
- **Tables**: `PP-LCNet_x1_0_table_cls`, `RT-DETR-L_wired_table_cell_det`,
  `RT-DETR-L_wireless_table_cell_det`, `SLANeXt_wired`, `SLANet_plus`
- **Formula**: `PP-FormulaNet_plus-L`

Treat these as pinned dependencies: keep them out of the Docker image
(mounted read-only, not baked in), don't rely on runtime downloads, and
re-validate before bumping the `paddleocr` version in the `Dockerfile` —
upgrades can change model names, pipeline config, constructor arguments,
or output schema.

## PaddleX DocPreprocessor fix

PaddleOCR 3.6.0/PaddleX's nested `DocPreprocessor` sub-pipeline ignores
the top-level `PPStructureV3(model_dir=...)` overrides for
`PP-LCNet_x1_0_doc_ori` and `UVDoc`, recreating them with `model_dir=None`
— which then tries to download the model during `predict()`.
`docker/patch_doc_preprocessor.py` rewrites the installed PaddleX YAML
config at build time so the nested pipeline also points at the local
`/models/...` paths. It's build-time only (no host files touched, no
network needed at runtime) and is removed from the final image. Do not
work around this by disabling orientation/unwarping.

## Cache

The container's `HOME` is `/cache` (mounted read/write), so Paddle/PaddleX/
HuggingFace runtime caches and CUDA JIT kernel caches land there. Reset it
with `rm -rf cache/*` — only when no OCR process (one-shot or daemon) is
running.

## Troubleshooting

**GPU not visible** — check `nvidia-smi` on the host, then
`docker run --rm --gpus all --entrypoint bash local-paddleocr:3.6.0 -c "nvidia-smi"`.
If the second fails, it's a Docker/NVIDIA Container Toolkit issue, not
PaddleOCR.

**Model download error** — with `--network none` this means a required
local model is missing; check `ls -lah models/`. Don't enable networking
as a workaround.

**`Creating model: ('PP-LCNet_x1_0_doc_ori', None, None)` in logs** — the
image wasn't patched correctly, or was built against a different PaddleX
version. Rebuild with `docker build --no-cache -t local-paddleocr:3.6.0 ./docker`.

**Permission errors on output** — keep `--user "$(id -u):$(id -g)"` and
make sure `Samples/Output`/`cache` are writable by the host user. Don't
run as root to work around it.

**Slow processing** — PP-StructureV3 does substantially more work than
plain OCR; tables, formulas, multi-column layouts and poor scans all add
time. Watch `watch -n 1 nvidia-smi`. If you're processing many files over
time, use daemon mode — it removes the ~35s reload cost per file.

**Daemon fast path not being used** — `ocr-server.sh status` to confirm
it's running, and check the `OUTPUT` you're passing to `ocr.sh` matches
exactly what you passed to `ocr-server.sh start` (compared as absolute
paths).

## License

This project's own code is licensed under the [Apache License 2.0](LICENCE.md)
— matching PaddleOCR, PaddleX and the `PaddlePaddle`-published model
weights it depends on, which are themselves Apache-2.0 licensed.

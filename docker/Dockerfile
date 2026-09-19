FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.3.0-gpu-cuda12.9-cudnn9.9

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

# Prevent PaddleX from performing model-source connectivity checks.
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# Paddle/PaddleX runtime cache.
ENV HOME=/cache

WORKDIR /app


# ------------------------------------------------------------
# Install PaddleOCR
# ------------------------------------------------------------

RUN python -m pip install --no-cache-dir \
    "paddleocr[doc-parser]==3.6.0"


# ------------------------------------------------------------
# Copy application files
# ------------------------------------------------------------

COPY pipeline.py /app/pipeline.py
COPY ocr.py /app/ocr.py
COPY server.py /app/server.py
COPY client.py /app/client.py
COPY entrypoint.sh /app/entrypoint.sh
COPY patch_doc_preprocessor.py /app/patch_doc_preprocessor.py

RUN chmod +x /app/entrypoint.sh


# ------------------------------------------------------------
# Create runtime user
# ------------------------------------------------------------

RUN useradd \
    --create-home \
    --uid 10001 \
    --shell /usr/sbin/nologin \
    ocruser


# ------------------------------------------------------------
# Runtime directories
# ------------------------------------------------------------

RUN mkdir -p /cache /models /app && \
    chown -R ocruser:ocruser /cache /models /app


# ------------------------------------------------------------
# IMPORTANT:
# Patch PaddleX's nested DocPreprocessor configuration.
#
# This makes:
#
# PP-LCNet_x1_0_doc_ori -> /models/PP-LCNet_x1_0_doc_ori
# UVDoc                 -> /models/UVDoc
#
# inside the nested doc_preprocessor pipeline.
# ------------------------------------------------------------

RUN python /app/patch_doc_preprocessor.py


# ------------------------------------------------------------
# Remove build-only patch script
# ------------------------------------------------------------

RUN rm /app/patch_doc_preprocessor.py


# ------------------------------------------------------------
# Default user
#
# docker run will override this with host UID/GID.
# ------------------------------------------------------------

USER ocruser

ENTRYPOINT ["/app/entrypoint.sh"]
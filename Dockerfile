FROM python:3.12-slim AS builder

WORKDIR /build

COPY common/ /build/common/
RUN pip install --no-cache-dir --prefix=/install /build/common

COPY pyproject.toml /build/service/
COPY src/ /build/service/src/
ENV PYTHONPATH=/install/lib/python3.12/site-packages
RUN pip install --no-cache-dir --prefix=/install /build/service

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r utils && useradd -r -g utils utils

WORKDIR /app

COPY --from=builder /install /usr/local

ENV PYTHONUNBUFFERED=1

USER utils

EXPOSE 8000

STOPSIGNAL SIGTERM

CMD ["uvicorn", "nitro_utils.main:app", "--host", "0.0.0.0", "--port", "8000"]

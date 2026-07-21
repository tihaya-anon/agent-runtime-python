FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
    OTEL_SERVICE_NAME=agent-runtime-python \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY README.md ./
COPY src ./src

EXPOSE 8088

CMD ["agent-runtime-python-internal-api", "--host", "0.0.0.0", "--port", "8088"]

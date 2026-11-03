# 実装役 (AgentCore Runtime) のイメージ。AgentCore Runtime は ARM64 のイメージしか動かせない
# ビルド: just implementer-build (docker buildx build --platform linux/arm64)
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.15 /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 依存パッケージだけを先に入れて、コードの変更でこの層を作り直さないようにする
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app.py callback.py ./

RUN useradd --create-home --uid 1000 agent
USER agent

# SDK はコンテナの中かを /.dockerenv で判定して 0.0.0.0 で待ち受ける。
# AgentCore の microVM では判定が外れうるので明示する
ENV PATH="/app/.venv/bin:$PATH" \
    DOCKER_CONTAINER=1

EXPOSE 8080
CMD ["python", "app.py"]

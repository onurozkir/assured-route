FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir uv==0.12.2 \
    && uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python

FROM python:3.12-slim
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY --from=build /build/.venv /app/.venv
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "assured_route.api:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project

COPY intelgraph/ intelgraph/
COPY README.md ./

RUN uv sync --no-dev --frozen

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "intelgraph.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
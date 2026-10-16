FROM node:22-bookworm-slim AS ui
WORKDIR /build/ui
COPY ui/package*.json ./
RUN npm ci --ignore-scripts
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV OTEL_SDK_DISABLED=true PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 RSA_DATA_DIR=/data RSA_TEMPLATE=/templates/lab-template.pptx RSA_ENV=production UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress poppler-utils fonts-noto-cjk fonts-crosextra-carlito fonts-liberation2 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.13.1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY --from=ui /build/src/research_slide_agent/static/viewer.html ./src/research_slide_agent/static/viewer.html
RUN uv sync --frozen --no-dev --no-editable && useradd --uid 10001 --create-home app && mkdir /data /templates && chown app:app /data /templates
COPY examples/lab-template.pptx /templates/lab-template.pptx
USER 10001:10001
EXPOSE 8000
CMD ["rsa", "serve"]

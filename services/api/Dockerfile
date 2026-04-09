# ── Dev stage: full deps installed directly (for docker-compose dev) ──────────
FROM python:3.12-slim AS dev

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
ENV PYTHONPATH="/app/src"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libzbar0 \
       tesseract-ocr \
       tesseract-ocr-spa \
       poppler-utils \
       libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ── Build stage: install Python deps with prefix (for prod) ─────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install --prefix=/install -r requirements.txt

# ── Runtime stage: lean production image ─────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
ENV PYTHONPATH="/app/src"

# System deps required at runtime (OCR, barcode, PDF, magic)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libzbar0 \
       tesseract-ocr \
       tesseract-ocr-spa \
       poppler-utils \
       libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

COPY . .

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# Collect Django static files (admin CSS/JS) into STATIC_ROOT
RUN DJANGO_SECRET_KEY=build-placeholder DJANGO_DEBUG=False \
    python src/manage.py collectstatic --noinput

# Non-root user for security
RUN useradd -r -s /usr/sbin/nologin -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["sh", "docker-entrypoint.sh"]

# Production WSGI server
CMD ["gunicorn", \
     "--bind=0.0.0.0:8000", \
     "--workers=4", \
     "--timeout=120", \
     "--access-logfile=-", \
     "--error-logfile=-", \
     "config.wsgi:application"]

FROM python:3.11-slim

# Empêche Python d'écrire des .pyc et force flush stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# User non-root pour la sécurité
RUN groupadd -r nova && useradd -r -g nova nova

WORKDIR /app

# Installation des dépendances (cache layer)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code applicatif
COPY app/ ./app/

# Permissions
RUN chown -R nova:nova /app
USER nova

# Healthcheck (Coolify s'en sert)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Librairies système requises par WeasyPrint (export PDF).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        libjpeg62-turbo \
        libxml2 \
        libxslt1.1 \
        shared-mime-info \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
# L'app vit dans web/ et utilise des imports plats (catalogue_routes, etc.)
CMD gunicorn --chdir web app:app --bind 0.0.0.0:$PORT --timeout 120

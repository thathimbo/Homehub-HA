# Home Assistant add-on image. The Supervisor builds it from this folder on install.
FROM python:3.14-alpine AS builder

WORKDIR /app

# Build dependencies
RUN apk add --no-cache \
    build-base \
    zlib-dev \
    jpeg-dev \
    nodejs \
    npm

COPY src/requirements.txt .
# Installed under /install so the runtime stage can copy just the packages and their scripts
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Copy package files and build Tailwind CSS
COPY src/package.json src/tailwind.config.js ./
COPY src/static/input.css ./static/
COPY src/templates ./templates
# Page scripts use Tailwind classes too, so Tailwind must see them when it builds the CSS
COPY src/static/js ./static/js
RUN npm install && npm run build:css

FROM python:3.14-alpine

WORKDIR /app

ARG BUILD_VERSION=dev
ENV SW_CACHE_VERSION=$BUILD_VERSION
# Log lines reach the add-on log as they are written
ENV PYTHONUNBUFFERED=1

# Where the add-on keeps things:
#   /data   add-on storage, backed up with the add-on (database, settings, compressed PDFs)
#   /share  Shared Cloud uploads, reachable from the Samba / File editor add-ons
#   /media  Media Downloader files, visible in Home Assistant's Media browser
ENV HOMEHUB_CONFIG=/data/homehub/config.yml \
    HOMEHUB_DATA_DIR=/data/homehub \
    HOMEHUB_PDFS_DIR=/data/homehub/pdfs \
    HOMEHUB_UPLOADS_DIR=/share/homehub/uploads \
    HOMEHUB_MEDIA_DIR=/media/homehub \
    HOMEHUB_ADDON_OPTIONS=/data/options.json

# Runtime-only packages (tzdata so Home Assistant's time zone applies)
RUN apk add --no-cache \
    ffmpeg \
    ghostscript \
    libjpeg-turbo \
    zlib \
    libstdc++ \
    tzdata

# Copy installed packages and their scripts (gunicorn, pybabel) from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY src /app
# The Home Assistant integration the add-on installs into custom_components
COPY integration/homehub /integration/homehub

# Compile the translation catalogs (.po) into the .mo files the app reads
RUN pybabel compile -d translations

# Copy built Tailwind CSS from builder
COPY --from=builder /app/static/output.css /app/static/output.css

EXPOSE 5000

LABEL \
    io.hass.name="HomeHub" \
    io.hass.description="Family dashboard for the people in your home" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}"

# Writes config.yml from the add-on options, then starts gunicorn: one process (SQLite,
# in-process download threads) with threads so a slow upload or PDF job does not block everyone
CMD ["python", "-m", "app.addon"]

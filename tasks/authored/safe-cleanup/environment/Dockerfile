FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends coreutils findutils \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip install --no-cache-dir "pytest==8.4.1" "pytest-json-ctrf==0.3.5"

WORKDIR /app
COPY cleanup.sh /app/cleanup.sh
RUN chmod +x /app/cleanup.sh

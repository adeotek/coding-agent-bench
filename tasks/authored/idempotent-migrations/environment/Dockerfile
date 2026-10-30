FROM python:3.12-slim

RUN python -m pip install --no-cache-dir "pytest==8.4.1" "pytest-json-ctrf==0.3.5"

WORKDIR /app
COPY shop/ /app/shop/
RUN python /app/shop/migrate.py && python /app/shop/seed.py

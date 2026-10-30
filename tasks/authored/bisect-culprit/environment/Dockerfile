FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip install --no-cache-dir "pytest==8.4.1" "pytest-json-ctrf==0.3.5"

ENV TZ=UTC \
    GIT_AUTHOR_NAME="calc" \
    GIT_AUTHOR_EMAIL="calc@example.com" \
    GIT_COMMITTER_NAME="calc" \
    GIT_COMMITTER_EMAIL="calc@example.com"

COPY build_repo.sh /opt/build_repo.sh
RUN bash /opt/build_repo.sh

WORKDIR /app/calc

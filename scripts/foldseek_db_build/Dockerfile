# Standalone foldseek DB builder — independent of the app image.
# Build:  docker build -t foldseek-db-build scripts/foldseek_db_build
# Run:    docker run -v "$(pwd)/scripts/foldseek_db_build/output:/app/output" foldseek-db-build
#
# The output mount is how the built DB and the cached ProstT5 weights land on the
# host (scripts/foldseek_db_build/output/), so the next run skips the weights download.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# foldseek static binary, arch-aware (works on Apple-Silicon aarch64 and x86_64).
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ];  then URL=https://mmseqs.com/foldseek/foldseek-linux-avx2.tar.gz; \
    elif [ "$ARCH" = "aarch64" ]; then URL=https://mmseqs.com/foldseek/foldseek-linux-arm64.tar.gz; \
    else echo "unsupported arch: $ARCH" && exit 1; fi && \
    wget -q "$URL" -O /tmp/fs.tgz && tar -xzf /tmp/fs.tgz -C /tmp && \
    cp /tmp/foldseek/bin/foldseek /usr/local/bin/foldseek && \
    chmod +x /usr/local/bin/foldseek && rm -rf /tmp/foldseek*

WORKDIR /app
COPY build_db.py *.csv ./
ENTRYPOINT ["python", "build_db.py"]

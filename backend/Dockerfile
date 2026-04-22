FROM python:3.11-slim

WORKDIR /app

# System dependencies: curl + unzip needed to download and extract scanner binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl unzip && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY scanner/ scanner/

RUN mkdir -p data/scans backend/instance scanner/bin

# Download scanner binaries at build time (arch-aware)
RUN set -eux; \
    ARCH=$(uname -m); \
    case "$ARCH" in \
        x86_64)        ARCH_AMD="amd64"; ARCH_FULL="x86_64" ;; \
        aarch64|arm64) ARCH_AMD="arm64"; ARCH_FULL="arm64" ;; \
        *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac; \
    \
    # gospider
    TAG=$(curl -sfL https://api.github.com/repos/jaeles-project/gospider/releases/latest \
          | grep '"tag_name"' | head -1 | sed -E 's/.*"tag_name":\s*"([^"]+)".*/\1/'); \
    curl -sfL "https://github.com/jaeles-project/gospider/releases/download/${TAG}/gospider_${TAG}_linux_${ARCH_FULL}.zip" \
         -o /tmp/gospider.zip; \
    unzip -qo /tmp/gospider.zip -d /tmp/gospider_extract; \
    find /tmp/gospider_extract -name "gospider" -type f -exec mv {} scanner/bin/gospider \;; \
    chmod +x scanner/bin/gospider; \
    rm -rf /tmp/gospider.zip /tmp/gospider_extract; \
    \
    # trufflehog (secret scanner)
    TAG=$(curl -sfL https://api.github.com/repos/trufflesecurity/trufflehog/releases/latest \
          | grep '"tag_name"' | head -1 | sed -E 's/.*"tag_name":\s*"([^"]+)".*/\1/'); \
    VERSION="${TAG#v}"; \
    curl -sfL "https://github.com/trufflesecurity/trufflehog/releases/download/${TAG}/trufflehog_${VERSION}_linux_${ARCH_AMD}.tar.gz" \
         -o /tmp/trufflehog.tar.gz; \
    tar -xzf /tmp/trufflehog.tar.gz -C scanner/bin trufflehog; \
    chmod +x scanner/bin/trufflehog; \
    rm -f /tmp/trufflehog.tar.gz; \
    \
    # dnsx
    TAG=$(curl -sfL https://api.github.com/repos/projectdiscovery/dnsx/releases/latest \
          | grep '"tag_name"' | head -1 | sed -E 's/.*"tag_name":\s*"([^"]+)".*/\1/'); \
    VERSION="${TAG#v}"; \
    curl -sfL "https://github.com/projectdiscovery/dnsx/releases/download/${TAG}/dnsx_${VERSION}_linux_${ARCH_AMD}.zip" \
         -o /tmp/dnsx.zip; \
    unzip -qo /tmp/dnsx.zip -d /tmp/dnsx_extract; \
    find /tmp/dnsx_extract -name "dnsx" -type f -exec mv {} scanner/bin/dnsx \;; \
    chmod +x scanner/bin/dnsx; \
    rm -rf /tmp/dnsx.zip /tmp/dnsx_extract

EXPOSE 3001

CMD ["gunicorn", "--config", "backend/gunicorn.conf.py", "backend.wsgi:app"]

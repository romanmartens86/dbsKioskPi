ARG BUILD_FROM=python:3.11-slim
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1

# Install required system tools (SSH client, sshpass, git, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    sshpass \
    git \
    curl \
    rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy python dependencies and install
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application files
COPY app /app/

# Copy repository files to provisioner package directory
RUN mkdir -p /app/package
COPY install.sh /app/package/
COPY files /app/package/files/
COPY bin /app/package/bin/

COPY run.sh /run.sh
RUN chmod +x /run.sh /app/main.py

EXPOSE 8099

CMD [ "/run.sh" ]

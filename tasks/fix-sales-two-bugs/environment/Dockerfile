FROM ubuntu:24.04

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*
COPY tools /app/tools
COPY data /app/data
RUN sed -i 's/\r$//' /app/tools/make_report.sh && chmod +x /app/tools/make_report.sh

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    TORSEARCH_CONFIG=/config/config.yaml

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY torsearch ./torsearch
RUN pip install --no-cache-dir .

# Non-root user; the entrypoint fixes /data ownership (bind mounts come up as root)
# then drops privileges, so the app never runs as root.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data /config \
    && chown -R app:app /app /data /config
COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "torsearch.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

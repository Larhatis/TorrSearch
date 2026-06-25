FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    TORSEARCH_CONFIG=/config/config.yaml

COPY pyproject.toml ./
COPY torsearch ./torsearch
RUN pip install --no-cache-dir .

# Run as a non-root user; /data (settings, users, library) and /config are writable.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data /config \
    && chown -R app:app /app /data /config
USER app

EXPOSE 8000
CMD ["uvicorn", "torsearch.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

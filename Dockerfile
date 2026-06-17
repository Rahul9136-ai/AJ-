# AJ — Purvi Technologies multi-agent assistant (Streamlit)
FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# Streamlit serves on 8501.
EXPOSE 8501

# Headless server config suitable for a cloud host behind HTTPS.
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true

# Persisted to-dos/memory live here; mount a volume to keep them across restarts.
RUN mkdir -p /app/workspace

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

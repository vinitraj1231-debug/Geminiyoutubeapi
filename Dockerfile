FROM python:3.10-slim

# System updates and FFmpeg installation
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependencies and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Expose port 8000
EXPOSE 8000

# Run FastAPI app with Uvicorn
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8000"]

FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

WORKDIR /app_root

# Install Python deps (Playwright Python package + app deps)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

EXPOSE 8000

# Run migrations then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

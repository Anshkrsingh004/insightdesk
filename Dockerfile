FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; chromadb 1.5 ships prebuilt wheels (no compiler needed).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8501

# Default: API. docker-compose overrides the command for the UI service.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

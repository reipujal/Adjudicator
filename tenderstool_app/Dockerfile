FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

COPY requirements.in ./
RUN pip install --no-cache-dir -r requirements.in

COPY app ./app

RUN mkdir -p app/downloads app/diagnostics

EXPOSE 8000

# Un único worker: el guard de concurrencia del MVP es un lock en memoria de
# proceso y no protege frente a varios workers (ver README).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# Minimal image for the CoO-PILOT backend.
#
#   docker build -t coo-pilot-backend .
#   docker run -p 8000:8000 --env-file .env coo-pilot-backend
#
# Python 3.11+ is required (the backend uses enum.StrEnum).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The pipeline imports the extraction and rules modules by name, so every
# package it reaches through an adapter must be present. Omitting one does
# not fail the build - the adapter falls back silently - so keep this list in
# step with backend/services/*_adapter.py.
COPY backend/ ./backend/
COPY extraction/ ./extraction/
COPY rules/ ./rules/
COPY schema.py ./

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

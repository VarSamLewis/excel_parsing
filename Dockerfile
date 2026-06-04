FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.in .
RUN pip install --no-cache-dir -r requirements.in

COPY . .

EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]

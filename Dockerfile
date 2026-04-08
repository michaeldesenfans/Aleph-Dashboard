FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ server/
COPY dashboard/ dashboard/

RUN mkdir -p data

EXPOSE 8080

CMD ["python", "-m", "server.api_server"]

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd -g 10001 shop && useradd -u 10001 -g shop -M shop && install -d -o shop -g shop /state
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY *.py ./
COPY evaluation_cases.json .
COPY demo_data ./demo_data
COPY knowledge ./knowledge
COPY web ./web
ENV SHOP_KB_INDEX=/state/knowledge.json SHOP_EMBEDDING_CACHE=/state/embeddings
USER 10001:10001
EXPOSE 8000
CMD ["python","-m","uvicorn","main:app","--host","0.0.0.0","--port","8000","--workers","1","--no-proxy-headers","--limit-concurrency","40","--timeout-graceful-shutdown","125"]

# media-docs: the text of office documents and PDF, and new docx, xlsx, pptx (a module of the Mercurius agent).
FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10041 --home /app docs
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY media_docs ./media_docs
USER docs
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8092
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8092/health', timeout=3)"
CMD ["python3", "-m", "media_docs.server"]

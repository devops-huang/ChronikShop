# One image for both jobs:
#   production worker  -> CMD (python -m chronik.cli --live), triggered by the mail flow
#   offline demo       -> docker compose run --rm demo   (see ../docker-compose.yml)
FROM python:3.11-slim

# PyMuPDF ships manylinux wheels; nothing else here needs system libraries.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Production defaults. Everything is configuration, so the same image can run in
# the client's subscription without being rebuilt.
#
#   AZURE_OPENAI_ENDPOINT   https://<your-resource>.openai.azure.com
#   AZURE_OPENAI_DEPLOYMENT gpt-4.1
#   ERP_DATA_DIR            /data/erp     (reference CSVs, refreshed nightly)
#   OUT_DIR                 /data/out     (ERP drop folder + review pack)
#   CHRONIK_LANG            both | en | zh
CMD ["python", "-m", "chronik.cli", "--live"]

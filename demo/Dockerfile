FROM python:3.11-slim

# PyMuPDF needs no system libs; nothing else here does either.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY chronik ./chronik
COPY config ./config

# The worker is stateless: it reads a PDF from a temp path and writes artefacts
# to a mounted volume / blob container. All configuration comes from env vars.
#
#   AZURE_OPENAI_ENDPOINT   https://<your-resource>.openai.azure.com
#   AZURE_OPENAI_DEPLOYMENT gpt-4.1
#   ERP_DATA_DIR            /data/erp        (reference CSVs, refreshed nightly)
#   OUT_DIR                 /data/out        (ERP drop folder + review pack)
#
# In production this image runs as an Azure Container App; the mail trigger is a
# small Power Automate flow (or a Graph subscription) that posts the message id.
CMD ["python", "-m", "chronik.cli", "--live"]

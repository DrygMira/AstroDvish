FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY product /app/product
COPY web_ui /app/web_ui
COPY data /app/data
COPY scripts /app/scripts
COPY PROMPT.md /app/PROMPT.md
COPY PROMPT_RECTIFICATION_STAGE1.md /app/PROMPT_RECTIFICATION_STAGE1.md

RUN chmod +x /app/scripts/start_api_local.sh /app/scripts/start_web_ui.sh

EXPOSE 8013
EXPOSE 8014

CMD ["/app/scripts/start_api_local.sh"]

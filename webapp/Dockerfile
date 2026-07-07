# No npm anywhere: all JS/CSS is vendored into app/static/vendor/
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd -r appuser && mkdir -p /srv/app/data && chown -R appuser /srv/app/data
USER appuser

ENV ANALYST_DATA_DIR=/srv/app/data

# default = web; the worker service overrides the command in docker-compose.yml
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]

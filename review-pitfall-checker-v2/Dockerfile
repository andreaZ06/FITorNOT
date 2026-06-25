FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fluxbox \
        novnc \
        socat \
        websockify \
        x11vnc \
        xauth \
        xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["python", "service_launcher.py"]

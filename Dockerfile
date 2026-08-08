FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY multicloud_healer/ multicloud_healer/

ENTRYPOINT ["python", "-m", "multicloud_healer.controller"]
CMD ["--namespace", "default", "--failure-threshold", "3", "--poll-interval", "10"]

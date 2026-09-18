# DaoCloud mirror avoids Docker Hub auth dependency in the domestic network.
# Replace with python:3.12-slim in environments that use a Docker Hub mirror.
FROM m.daocloud.io/docker.io/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY sql ./sql

RUN mkdir -p /app/uploads/assets /app/logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

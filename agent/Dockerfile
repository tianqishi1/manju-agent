# 国内网络：基础镜像走加速源，可用 --build-arg BASE_REGISTRY=docker.io 覆盖
ARG BASE_REGISTRY=docker.m.daocloud.io
FROM ${BASE_REGISTRY}/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY app ./app
COPY assets ./assets
RUN mkdir -p /app/data /app/media
EXPOSE 8000
ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

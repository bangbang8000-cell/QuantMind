FROM gcr.m.daocloud.io/kaggle-gpu-images/python:latest

RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g; s/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && apt-get clean && apt-get update && apt-get install -y \  
    curl \  
    vim \  
    git \  
    build-essential \
    strace \
    && rm -rf /var/lib/apt/lists/* 
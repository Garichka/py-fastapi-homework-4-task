FROM python:3.10-slim

# Setting environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=off

# Installing dependencies
RUN apt update && apt install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN python -m pip install --upgrade pip && \
    pip install poetry

# Configure Poetry to avoid creating a virtual environment
RUN poetry config virtualenvs.create false

# Selecting a working directory
WORKDIR /usr/src/poetry

# Copy dependency files
COPY ./poetry.lock ./pyproject.toml ./

# Install dependencies with Poetry
RUN poetry install --no-interaction --no-ansi --no-root --only main

# Copy pytest config file
COPY ./pytest.ini /usr/src/config/pytest.ini

# Selecting a working directory
WORKDIR /usr/src/fastapi

# Copy the source code
COPY ./src .

FROM agnohq/python:3.12

# Environment variables that actually matter
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

ARG USER=app
ARG APP_DIR=/app
ARG DATA_DIR=/data

# Create user
RUN groupadd -g 61000 ${USER} \
    && useradd -g 61000 -u 61000 -ms /bin/bash -d ${APP_DIR} ${USER} \
    && mkdir -p ${DATA_DIR} \
    && chown -R ${USER}:${USER} ${DATA_DIR}

WORKDIR ${APP_DIR}

# Install Poetry and main dependencies first (better layer caching)
RUN pip install --no-cache-dir poetry==2.1.3
COPY pyproject.toml README.md ./
RUN poetry install --only main --no-root

# Copy app code
COPY --chown=${USER}:${USER} . .

USER ${USER}

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["chill"]

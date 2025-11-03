FROM python:3.12-slim

WORKDIR /app

RUN pip install poetry==1.8.5

COPY pyproject.toml poetry.toml ./

RUN poetry install --no-interaction --no-ansi --no-root

COPY . .

CMD ["poetry", "run", "python", "main.py"]

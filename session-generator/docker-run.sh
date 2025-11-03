#!/bin/bash

# Запуск генератора через Docker

echo "🐳 Запуск через Docker..."
echo ""

docker build -t session-generator .

docker run -it --rm \
  -v $(pwd):/app \
  session-generator

echo ""
echo "✅ Session файл создан в текущей директории"

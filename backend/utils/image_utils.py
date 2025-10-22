"""
Утилиты для работы с изображениями подарков
"""
from typing import Optional
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


def get_asset_url(request: Request, relative_path: Optional[str]) -> Optional[str]:
    """
    Преобразует относительный путь изображения в полный URL

    Args:
        request: FastAPI Request объект для получения базового URL
        relative_path: Относительный путь от папки assets (например, "/gifts/unique/Loli Pop.png")

    Returns:
        Полный URL до изображения или None если путь не указан
    """
    if not relative_path:
        return None

    # Если это старый URL (https://...), возвращаем как есть
    if relative_path.startswith('http'):
        logger.info(f"🔗 Image URL already full: {relative_path}")
        return relative_path

    # Убираем начальный слеш если есть
    clean_path = relative_path.lstrip('/')

    # 🔥 ИСПОЛЬЗУЕМ CDN вместо локального сервера
    cdn_base_url = 'https://vip.cdn-starcrash.com.ru'

    # Формируем полный URL - статические файлы на CDN
    # путь /gifts/unique/file.png должен стать https://vip.cdn-starcrash.com.ru/gifts/unique/file.png
    result_url = f"{cdn_base_url}/{clean_path}"
    logger.info(f"🖼️ Converting image path: {relative_path} -> {result_url}")
    return result_url


def normalize_asset_path(file_path: str) -> str:
    """
    Нормализует путь файла к относительному от папки assets

    Args:
        file_path: Путь к файлу (может быть полным или относительным)

    Returns:
        Нормализованный относительный путь от assets
    """
    # Убираем начальные слеши и assets/
    clean_path = file_path.lstrip('/')
    if clean_path.startswith('assets/'):
        clean_path = clean_path[7:]  # убираем 'assets/'

    return f"/{clean_path}"
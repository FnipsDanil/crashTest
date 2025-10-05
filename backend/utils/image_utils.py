"""
Утилиты для работы с изображениями подарков
"""
import os
from typing import Optional
from fastapi import Request


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
        return relative_path
    
    # Убираем начальный слеш если есть
    clean_path = relative_path.lstrip('/')
    
    # Получаем базовый URL сервера
    base_url = str(request.base_url).rstrip('/')
    
    # Формируем полный URL - статические файлы монтированы в /assets
    # и указывают на frontend/assets, поэтому путь /gifts/unique/file.png
    # должен стать /assets/gifts/unique/file.png
    return f"{base_url}/assets/{clean_path}"


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


def is_valid_asset_path(file_path: str, assets_root: str) -> bool:
    """
    Проверяет, что путь к файлу безопасен и находится в папке assets
    
    Args:
        file_path: Путь к файлу
        assets_root: Корневая папка assets
    
    Returns:
        True если путь безопасен
    """
    try:
        # Получаем абсолютный путь
        abs_path = os.path.abspath(os.path.join(assets_root, file_path.lstrip('/')))
        abs_assets = os.path.abspath(assets_root)
        
        # Проверяем что путь находится внутри assets
        return abs_path.startswith(abs_assets) and os.path.exists(abs_path)
    except:
        return False
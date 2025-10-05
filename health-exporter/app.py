#!/usr/bin/env python3
"""
Легковесный экспортер для мониторинга health всех контейнеров
Проверяет доступность сервисов и возвращает метрики в формате Prometheus
"""

import asyncio
import aiohttp
import time
from typing import Dict, List, Tuple
from aiohttp import web
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Конфигурация сервисов для проверки
SERVICES = {
    'backend': {
        'url': 'http://backend:8000/health',
        'timeout': 5,
        'expected_status': 200
    },
    'frontend': {
        'url': 'http://frontend:5173',
        'timeout': 3,
        'expected_status': 200
    },
    'postgres': {
        'url': 'http://postgres:5432',
        'timeout': 2,
        'expected_status': None,  # TCP проверка
        'tcp_check': True,
        'host': 'postgres',
        'port': 5432
    },
    'redis': {
        'url': 'http://redis:6379',
        'timeout': 2,
        'expected_status': None,  # TCP проверка
        'tcp_check': True,
        'host': 'redis',
        'port': 6379
    },
    'pgbouncer': {
        'url': 'http://pgbouncer:6432',
        'timeout': 2,
        'expected_status': None,  # TCP проверка
        'tcp_check': True,
        'host': 'pgbouncer',
        'port': 6432
    },
    'grafana': {
        'url': 'http://grafana:3000/api/health',
        'timeout': 3,
        'expected_status': 200
    },
    'prometheus': {
        'url': 'http://prometheus:9090/-/healthy',
        'timeout': 3,
        'expected_status': 200
    },
    'nginx': {
        'url': 'http://nginx:80',
        'timeout': 3,
        'expected_status': [200, 301, 302, 404]  # nginx может отдать разные коды
    }
}

class HealthChecker:
    def __init__(self):
        self.session = None
        self.metrics_cache = {}
        self.cache_ttl = 10  # Кэшируем на 10 секунд
        
    async def start(self):
        """Инициализация HTTP сессии"""
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        logger.info("Health checker initialized")
    
    async def stop(self):
        """Закрытие HTTP сессии"""
        if self.session:
            await self.session.close()
            logger.info("Health checker stopped")
    
    async def check_tcp_connection(self, host: str, port: int, timeout: int = 2) -> bool:
        """Проверка TCP соединения"""
        try:
            future = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(future, timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception as e:
            logger.debug(f"TCP check failed for {host}:{port} - {e}")
            return False
    
    async def check_http_service(self, name: str, config: dict) -> Tuple[bool, float, str]:
        """Проверка HTTP сервиса"""
        start_time = time.time()
        
        try:
            # TCP проверка для БД сервисов
            if config.get('tcp_check', False):
                is_healthy = await self.check_tcp_connection(
                    config['host'], 
                    config['port'], 
                    config['timeout']
                )
                response_time = time.time() - start_time
                status = 'tcp_ok' if is_healthy else 'tcp_failed'
                return is_healthy, response_time, status
            
            # HTTP проверка
            async with self.session.get(
                config['url'], 
                timeout=aiohttp.ClientTimeout(total=config['timeout'])
            ) as response:
                response_time = time.time() - start_time
                
                expected_status = config.get('expected_status')
                if expected_status is None:
                    is_healthy = True
                elif isinstance(expected_status, list):
                    is_healthy = response.status in expected_status
                else:
                    is_healthy = response.status == expected_status
                
                status_info = f"http_{response.status}"
                return is_healthy, response_time, status_info
                
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            logger.debug(f"Timeout checking {name}")
            return False, response_time, 'timeout'
        except Exception as e:
            response_time = time.time() - start_time
            logger.debug(f"Error checking {name}: {e}")
            return False, response_time, 'error'
    
    async def check_all_services(self) -> Dict[str, Dict]:
        """Проверка всех сервисов"""
        # Проверяем кэш
        current_time = time.time()
        cache_key = 'all_services'
        
        if (cache_key in self.metrics_cache and 
            current_time - self.metrics_cache[cache_key]['timestamp'] < self.cache_ttl):
            return self.metrics_cache[cache_key]['data']
        
        results = {}
        
        # Запускаем все проверки параллельно
        tasks = []
        for service_name, config in SERVICES.items():
            task = self.check_http_service(service_name, config)
            tasks.append((service_name, task))
        
        # Ждем результаты
        for service_name, task in tasks:
            try:
                is_healthy, response_time, status = await task
                results[service_name] = {
                    'healthy': is_healthy,
                    'response_time': response_time,
                    'status': status,
                    'timestamp': current_time
                }
            except Exception as e:
                logger.error(f"Failed to check {service_name}: {e}")
                results[service_name] = {
                    'healthy': False,
                    'response_time': 0,
                    'status': 'check_failed',
                    'timestamp': current_time
                }
        
        # Кэшируем результат
        self.metrics_cache[cache_key] = {
            'data': results,
            'timestamp': current_time
        }
        
        return results
    
    def format_prometheus_metrics(self, results: Dict[str, Dict]) -> str:
        """Форматирование метрик в формате Prometheus"""
        metrics = []
        
        # Добавляем заголовок
        metrics.append("# HELP container_health_status Health status of containers (1=healthy, 0=unhealthy)")
        metrics.append("# TYPE container_health_status gauge")
        
        # Метрики статуса
        for service_name, data in results.items():
            health_value = 1 if data['healthy'] else 0
            metrics.append(
                f'container_health_status{{service="{service_name}",status="{data["status"]}"}} {health_value}'
            )
        
        # Время отклика
        metrics.append("# HELP container_response_time_seconds Response time in seconds")
        metrics.append("# TYPE container_response_time_seconds gauge")
        
        for service_name, data in results.items():
            metrics.append(
                f'container_response_time_seconds{{service="{service_name}"}} {data["response_time"]:.3f}'
            )
        
        # Timestamp последней проверки
        metrics.append("# HELP container_last_check_timestamp Last check timestamp")
        metrics.append("# TYPE container_last_check_timestamp gauge")
        
        for service_name, data in results.items():
            metrics.append(
                f'container_last_check_timestamp{{service="{service_name}"}} {data["timestamp"]}'
            )
        
        # Общая метрика uptime экспортера
        metrics.append("# HELP health_exporter_up Health exporter status")
        metrics.append("# TYPE health_exporter_up gauge")
        metrics.append("health_exporter_up 1")
        
        return '\n'.join(metrics) + '\n'

# Глобальный экземпляр checker
health_checker = HealthChecker()

async def metrics_handler(request):
    """Обработчик эндпоинта /metrics"""
    try:
        results = await health_checker.check_all_services()
        metrics_text = health_checker.format_prometheus_metrics(results)
        
        return web.Response(
            text=metrics_text,
            content_type='text/plain',
            charset='utf-8'
        )
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return web.Response(
            text="# Error generating metrics\n",
            status=500,
            content_type='text/plain',
            charset='utf-8'
        )

async def health_handler(request):
    """Обработчик эндпоинта /health для проверки самого экспортера"""
    return web.json_response({
        'status': 'healthy',
        'timestamp': time.time(),
        'services_monitored': len(SERVICES)
    })

async def init_app():
    """Инициализация приложения"""
    app = web.Application()
    
    # Роуты
    app.router.add_get('/metrics', metrics_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/', health_handler)  # Root тоже отдает health
    
    # Запускаем health checker
    await health_checker.start()
    
    return app

async def cleanup(app):
    """Очистка ресурсов"""
    await health_checker.stop()

def main():
    """Главная функция"""
    logger.info("Starting Health Exporter...")
    
    app = init_app()
    
    # Настройка cleanup
    async def create_app():
        application = await app
        application.on_cleanup.append(cleanup)
        return application
    
    web.run_app(
        create_app(),
        host='0.0.0.0',
        port=8080,
        access_log=logger
    )

if __name__ == '__main__':
    main()
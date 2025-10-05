"""
Автоматическое создание партиций для game_history
"""
import asyncio
from datetime import datetime, timedelta
from database import get_db
from sqlalchemy import text


async def create_monthly_partition(year: int, month: int):
    """Создать месячную партицию для game_history"""
    # Форматы для PostgreSQL
    start_date = f"{year:04d}-{month:02d}-01"
    
    # Следующий месяц
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year
    
    end_date = f"{next_year:04d}-{next_month:02d}-01"
    
    partition_name = f"game_history_{year:04d}_{month:02d}"
    
    create_partition_sql = f"""
    CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF game_history 
    FOR VALUES FROM ('{start_date}') TO ('{end_date}');
    """
    
    async for session in get_db():
        try:
            await session.execute(text(create_partition_sql))
            await session.commit()
            print(f"Created partition: {partition_name} ({start_date} to {end_date})")
        except Exception as e:
            if "already exists" in str(e):
                print(f"Partition {partition_name} already exists")
            else:
                print(f"Error creating partition {partition_name}: {e}")
        break


async def ensure_current_partitions():
    """Убедиться что есть партиции на текущий и следующие месяцы"""
    now = datetime.now()
    
    # Создаем партиции на текущий месяц и следующие 3 месяца
    for i in range(4):
        target_date = now + timedelta(days=30 * i)
        await create_monthly_partition(target_date.year, target_date.month)


async def main():
    print("Creating PostgreSQL partitions for game_history...")
    await ensure_current_partitions()
    print("Partition creation completed")


if __name__ == "__main__":
    asyncio.run(main())
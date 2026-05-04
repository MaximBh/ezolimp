import sys
import os

# Добавляем текущую директорию в путь, чтобы импортировать app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base, TaskView, User, Task, Solution, Match, UserStats

def migrate():
    print("Проверка и создание недостающих таблиц...")
    try:
        # Это создаст только те таблицы, которых еще нет в базе данных
        Base.metadata.create_all(bind=engine)
        print("База данных успешно синхронизирована.")
    except Exception as e:
        print(f"Ошибка при миграции: {e}")

if __name__ == "__main__":
    migrate()

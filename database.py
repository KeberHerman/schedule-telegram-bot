import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_file="bot_database.db"):
        self.connection = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.create_tables()
        logger.info("База данных подключена")

    def create_tables(self):
        """Создание всех таблиц"""
        # Пользователи
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            full_name TEXT,
            surname TEXT,
            group_name TEXT,
            status TEXT DEFAULT 'pending',
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Основное расписание (по дням недели)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS base_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week INTEGER,
            lesson_number INTEGER,
            subject TEXT,
            teacher TEXT,
            classroom TEXT,
            time_start TEXT,
            time_end TEXT
        )
        """)

        # Актуальное расписание (на конкретные даты)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS actual_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            day_of_week INTEGER,
            lesson_number INTEGER,
            subject TEXT,
            teacher TEXT,
            classroom TEXT,
            time_start TEXT,
            time_end TEXT,
            expires_at TEXT,
            is_active INTEGER DEFAULT 1
        )
        """)

        # Домашнее задание
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            task TEXT,
            date_assigned TEXT,
            date_due TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
        """)

        # Логи действий
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Расписание по дням (фото)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week INTEGER,
            image_path TEXT,
            week_type TEXT DEFAULT 'all',
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Актуальное расписание (фото на даты)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS actual_schedule_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            image_path TEXT,
            expires_at TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Недельное расписание (фото всей недели) - ДОБАВЛЕНО
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS week_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT,
            week_type TEXT DEFAULT 'all',
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.connection.commit()

    # === МЕТОДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ===
    def user_exists(self, user_id: int) -> bool:
        result = self.cursor.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return result is not None

    def add_user(self, user_id: int, username: str, full_name: str, surname: str = None):
        try:
            self.cursor.execute("""
                INSERT INTO users (user_id, username, full_name, surname, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (user_id, username, full_name, surname))
            self.connection.commit()
            logger.info(f"Добавлен пользователь: {user_id}")
            return True
        except sqlite3.IntegrityError:
            return False

    def get_user(self, user_id: int):
        return self.cursor.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    def approve_user(self, user_id: int):
        try:
            self.cursor.execute(
                "UPDATE users SET status = 'approved' WHERE user_id = ?",
                (user_id,)
            )
            self.connection.commit()
            print(f"✅ Пользователь {user_id} одобрен в БД")
            return True
        except Exception as e:
            print(f"❌ Ошибка при одобрении пользователя {user_id}: {e}")
            return False

    def get_user_status(self, user_id: int) -> str:
        result = self.cursor.execute(
            "SELECT status FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return result[0] if result else None

    def is_user_approved(self, user_id: int) -> bool:
        status = self.get_user_status(user_id)
        return status == 'approved'

    # === МЕТОДЫ ДЛЯ РАСПИСАНИЯ ПО ДНЯМ ===
    def add_schedule_image(self, day_of_week: int, image_path: str, week_type: str = "all"):
        """Добавляет фото расписания на день"""
        self.cursor.execute(
            "DELETE FROM schedule_images WHERE day_of_week = ? AND week_type = ?",
            (day_of_week, week_type)
        )

        self.cursor.execute(
            "INSERT INTO schedule_images (day_of_week, image_path, week_type) VALUES (?, ?, ?)",
            (day_of_week, image_path, week_type)
        )

        self.connection.commit()

    def get_schedule_image(self, day_of_week: int, week_type: str = "all"):
        """Получает фото расписания на день"""
        result = self.cursor.execute(
            "SELECT image_path FROM schedule_images WHERE day_of_week = ? AND week_type = ?",
            (day_of_week, week_type)
        ).fetchone()

        if result:
            return result[0]

        if week_type != "all":
            result = self.cursor.execute(
                "SELECT image_path FROM schedule_images WHERE day_of_week = ? AND week_type = 'all'",
                (day_of_week,)
            ).fetchone()
            return result[0] if result else None

        return None

    # === МЕТОДЫ ДЛЯ НЕДЕЛЬНОГО РАСПИСАНИЯ ===
    def add_week_schedule(self, image_path: str, week_type: str = "all"):
        """Добавляет фото расписания на всю неделю"""
        self.cursor.execute(
            "DELETE FROM week_schedule WHERE week_type = ?",
            (week_type,)
        )

        self.cursor.execute(
            "INSERT INTO week_schedule (image_path, week_type) VALUES (?, ?)",
            (image_path, week_type)
        )

        self.connection.commit()

    def get_week_schedule(self, week_type: str = "all"):
        """Получает фото недельного расписания"""
        result = self.cursor.execute(
            "SELECT image_path FROM week_schedule WHERE week_type = ?",
            (week_type,)
        ).fetchone()
        if result:
            return result[0]
        if week_type != "all":
            result = self.cursor.execute(
                "SELECT image_path FROM week_schedule WHERE week_type = 'all'",
            ).fetchone()
            return result[0] if result else None
        return None

    # === МЕТОДЫ ДЛЯ АКТУАЛЬНОГО РАСПИСАНИЯ ===
    def add_actual_schedule_image(self, date: str, image_path: str, expires_at: str = None):
        """Добавляет актуальное фото расписания на дату"""
        self.cursor.execute("DELETE FROM actual_schedule_images WHERE date = ?", (date,))
        self.cursor.execute(
            "INSERT INTO actual_schedule_images (date, image_path, expires_at) VALUES (?, ?, ?)",
            (date, image_path, expires_at)
        )
        self.connection.commit()

    def get_actual_schedule_image(self, date: str):
        """Получает актуальное фото расписания на дату"""
        result = self.cursor.execute(
            "SELECT image_path FROM actual_schedule_images WHERE date = ?",
            (date,)
        ).fetchone()

        return result[0] if result else None

    def add_base_schedule(self, day_of_week: int, lessons: list):
        self.cursor.execute(
            "DELETE FROM base_schedule WHERE day_of_week = ?",
            (day_of_week,)
        )

        for lesson in lessons:
            self.cursor.execute("""
                INSERT INTO base_schedule 
                (day_of_week, lesson_number, subject, classroom, time_start, time_end)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                day_of_week,
                lesson.get('number'),
                lesson.get('subject'),
                lesson.get('classroom'),
                lesson.get('time_start'),
                lesson.get('time_end')
            ))

        self.connection.commit()

    def get_schedule_for_day(self, day_of_week: int):
        return self.cursor.execute("""
            SELECT * FROM base_schedule 
            WHERE day_of_week = ? 
            ORDER BY lesson_number
        """, (day_of_week,)).fetchall()

    def get_actual_schedule_for_date(self, date: str):
        return self.cursor.execute("""
            SELECT * FROM actual_schedule 
            WHERE date = ? AND is_active = 1
            ORDER BY lesson_number
        """, (date,)).fetchall()

    def get_today_schedule(self):
        from datetime import datetime
        today = datetime.now()
        day_of_week = today.weekday()
        date_str = today.strftime("%Y-%m-%d")
        actual = self.get_actual_schedule_for_date(date_str)
        if actual:
            return actual, True
        base = self.get_schedule_for_day(day_of_week)
        return base, False

    def get_tomorrow_schedule(self):
        from datetime import datetime, timedelta
        tomorrow = datetime.now() + timedelta(days=1)
        day_of_week = tomorrow.weekday()
        date_str = tomorrow.strftime("%Y-%m-%d")

        actual = self.get_actual_schedule_for_date(date_str)
        if actual:
            return actual, True

        base = self.get_schedule_for_day(day_of_week)
        return base, False

    def add_actual_schedule(self, date: str, lessons: list, expires_at: str = None):
        # Удаляем старые записи на эту дату
        self.cursor.execute("DELETE FROM actual_schedule WHERE date = ?", (date,))

        from datetime import datetime
        day_of_week = datetime.strptime(date, "%Y-%m-%d").weekday()

        for lesson in lessons:
            self.cursor.execute("""
                INSERT INTO actual_schedule 
                (date, day_of_week, lesson_number, subject, classroom, 
                 time_start, time_end, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date,
                day_of_week,
                lesson.get('number'),
                lesson.get('subject', ''),
                lesson.get('classroom', ''),
                lesson.get('time_start', ''),
                lesson.get('time_end', ''),
                expires_at or date
            ))

        self.connection.commit()

    # === МЕТОДЫ ДЛЯ ДОМАШНЕГО ЗАДАНИЯ ===

    def add_homework(self, subject: str, task: str, date_due: str):
        """Добавляет домашнее задание"""
        self.cursor.execute("""
            INSERT INTO homework (subject, task, date_due)
            VALUES (?, ?, ?)
        """, (subject, task, date_due))
        self.connection.commit()

    def get_homework_for_date(self, date_due: str):
        """Получает ДЗ на конкретную дату"""
        return self.cursor.execute("""
            SELECT * FROM homework 
            WHERE date_due = ? AND is_active = 1
            ORDER BY subject
        """, (date_due,)).fetchall()

    def get_latest_homework_by_subject(self, subject: str):
        """Получает последнее ДЗ по предмету"""
        return self.cursor.execute("""
            SELECT * FROM homework 
            WHERE subject = ? AND is_active = 1
            ORDER BY date_due DESC 
            LIMIT 1
        """, (subject,)).fetchone()

    # === СЛУЖЕБНЫЕ МЕТОДЫ ===

    def add_log(self, user_id: int, action: str):
        self.cursor.execute(
            "INSERT INTO logs (user_id, action) VALUES (?, ?)",
            (user_id, action)
        )
        self.connection.commit()

    def close(self):
        self.connection.close()

    def backup(self, backup_file="backup.db"):
        import shutil
        shutil.copy2("bot_database.db", backup_file)
        logger.info(f"Создана резервная копия: {backup_file}")
import sqlite3
import threading
from pathlib import Path
from typing import Optional


class StudentDatabase:
    """Quản lý dữ liệu sinh viên trong SQLite theo cách thread-safe."""

    def __init__(self, database_path: str = "students.db") -> None:
        path = Path(database_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path

        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._closed = False
        self._create_table()

    def _create_table(self) -> None:
        # Khóa bảo vệ kết nối khi nhiều worker cùng truy cập.
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    major TEXT NOT NULL,
                    gpa REAL NOT NULL
                )
                """
            )
            self._connection.commit()

    def create_student(
        self, student_id: str, name: str, email: str, major: str, gpa: float
    ) -> bool:
        with self._lock:
            try:
                self._connection.execute(
                    """
                    INSERT INTO students (id, name, email, major, gpa)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (student_id, name, email, major, gpa),
                )
                self._connection.commit()
                return True
            except sqlite3.IntegrityError:
                self._connection.rollback()
                return False

    def get_student(self, student_id: str) -> Optional[dict]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, name, email, major, gpa
                FROM students
                WHERE id = ?
                """,
                (student_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def update_student(
        self, student_id: str, name: str, email: str, major: str, gpa: float
    ) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE students
                SET name = ?, email = ?, major = ?, gpa = ?
                WHERE id = ?
                """,
                (name, email, major, gpa, student_id),
            )
            self._connection.commit()
            return cursor.rowcount > 0

    def delete_student(self, student_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM students WHERE id = ?",
                (student_id,),
            )
            self._connection.commit()
            return cursor.rowcount > 0

    def list_students(self) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, name, email, major, gpa
                FROM students
                ORDER BY id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

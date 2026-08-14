"""
Task storage using SQLite database
"""
import sqlite3
import json
from typing import List, Optional
from pathlib import Path
from datetime import datetime
try:
    from .models import Task, TaskStatus, TaskPriority, TaskSize, TaskCategory
except ImportError:
    from models import Task, TaskStatus, TaskPriority, TaskSize, TaskCategory

# Database file path
STORAGE_DIR = Path(__file__).parent
DB_FILE = STORAGE_DIR / "tasks.db"


def calculate_task_order(task: Task) -> int:
    """
    Calculate task order based on priority and ETA

    Order = Priority base * 10,000,000 + Time adjustment
    - Priority: HIGH=-3, MEDIUM=-2, LOW=-1 (multiplied by 10M for absolute weight)
    - Time: Overdue=-hours*10, Future=+hours, No ETA=+10000 (capped at 999,999)

    Lower order number = higher priority (appears first)
    Priority has absolute weight - all HIGH tasks come before all MEDIUM, etc.
    """
    print(f"[Storage] calculate_task_order() called for task: {task.header}")
    print(f"[Storage] Task priority: {task.priority}, ETA: {task.eta}")

    # Priority base score - multiplied by 10M for absolute weight
    priority_multiplier = {
        TaskPriority.HIGH: -3,
        TaskPriority.MEDIUM: -2,
        TaskPriority.LOW: -1,
        'high': -3,
        'medium': -2,
        'low': -1
    }

    base_priority = priority_multiplier.get(task.priority, -2) * 10000000
    print(f"[Storage] Base priority score: {base_priority}")

    # Time adjustment (capped to never override priority)
    time_adjustment = 0
    if task.eta:
        try:
            # Handle timezone-aware datetime
            if task.eta.tzinfo is not None:
                from datetime import timezone
                now = datetime.now(timezone.utc)
            else:
                now = datetime.now()

            diff_seconds = (task.eta - now).total_seconds()
            diff_hours = diff_seconds / 3600
            print(f"[Storage] Time diff: {diff_hours:.2f} hours")

            if diff_hours < 0:
                # Overdue: subtract hours * 10 (more overdue = lower order = higher priority)
                time_adjustment = max(int(diff_hours * 10), -999999)
                print(f"[Storage] Overdue task, time adjustment: {time_adjustment}")
            else:
                # Future: add hours (sooner = lower order = higher priority)
                time_adjustment = min(int(diff_hours), 999999)
                print(f"[Storage] Future task, time adjustment: {time_adjustment}")
        except Exception as e:
            print(f"[Storage] ERROR calculating time adjustment: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            # If time calculation fails, just use priority score
    else:
        # No ETA: lowest priority within the priority level
        time_adjustment = 10000
        print(f"[Storage] No ETA, adding 10000")

    order = base_priority + time_adjustment
    print(f"[Storage] Final calculated order: {order}")
    return order


class TaskStorage:
    """Task storage manager using SQLite"""

    def __init__(self):
        self._init_database()

    def _init_database(self):
        """Initialize database and create tables if not exist"""
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                header TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                size TEXT NOT NULL,
                eta TEXT,
                category TEXT NOT NULL,
                created_at TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                in_progress_at TEXT,
                returned_from_in_progress INTEGER NOT NULL DEFAULT 0,
                done_at TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task object"""
        return Task(
            id=row[0],
            header=row[1],
            content=row[2],
            status=TaskStatus(row[3]),
            priority=TaskPriority(row[4]),
            size=TaskSize(row[5]),
            eta=datetime.fromisoformat(row[6]) if row[6] else None,
            category=TaskCategory(row[7]),
            created_at=datetime.fromisoformat(row[8]),
            order=row[9],
            in_progress_at=datetime.fromisoformat(row[10]) if row[10] else None,
            returned_from_in_progress=bool(row[11]),
            done_at=datetime.fromisoformat(row[12]) if row[12] else None,
            returned_at=datetime.fromisoformat(row[13]) if len(row) > 13 and row[13] else None
        )

    def _task_to_row(self, task: Task) -> tuple:
        """Convert Task object to database row"""
        return (
            task.id,
            task.header,
            task.content,
            task.status.value if isinstance(task.status, TaskStatus) else task.status,
            task.priority.value if isinstance(task.priority, TaskPriority) else task.priority,
            task.size.value if isinstance(task.size, TaskSize) else task.size,
            task.eta.isoformat() if task.eta else None,
            task.category.value if isinstance(task.category, TaskCategory) else task.category,
            task.created_at.isoformat(),
            task.order,
            task.in_progress_at.isoformat() if task.in_progress_at else None,
            1 if task.returned_from_in_progress else 0,
            task.done_at.isoformat() if task.done_at else None,
            task.returned_at.isoformat() if task.returned_at else None
        )

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks"""
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM tasks ORDER BY order_num')
        rows = cursor.fetchall()

        conn.close()

        return [self._row_to_task(row) for row in rows]

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            return self._row_to_task(row)
        return None

    def create_task(self, task: Task) -> Task:
        """Create new task"""
        print(f"[Storage] create_task() called")
        print(f"[Storage] Task ID: {task.id}")
        print(f"[Storage] Task header: {task.header}")
        print(f"[Storage] Task status: {task.status}, type: {type(task.status)}")
        print(f"[Storage] Task priority: {task.priority}, type: {type(task.priority)}")
        print(f"[Storage] Task size: {task.size}, type: {type(task.size)}")
        print(f"[Storage] Task category: {task.category}, type: {type(task.category)}")
        print(f"[Storage] Task ETA: {task.eta}")

        # Auto-calculate order based on priority and ETA
        try:
            task.order = calculate_task_order(task)
            print(f"[Storage] Order calculated successfully: {task.order}")
        except Exception as e:
            print(f"[Storage] ERROR calculating order: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

        print(f"[Storage] Converting task to row...")
        try:
            row_data = self._task_to_row(task)
            print(f"[Storage] Row data: {row_data}")
        except Exception as e:
            print(f"[Storage] ERROR converting task to row: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

        print(f"[Storage] Opening database connection...")
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()

        print(f"[Storage] Executing INSERT statement...")
        try:
            cursor.execute('''
                INSERT INTO tasks (
                    id, header, content, status, priority, size, eta, category,
                    created_at, order_num, in_progress_at, returned_from_in_progress, done_at, returned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', row_data)
            print(f"[Storage] INSERT executed successfully")
        except Exception as e:
            print(f"[Storage] ERROR executing INSERT: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            conn.close()
            raise

        print(f"[Storage] Committing transaction...")
        conn.commit()
        conn.close()
        print(f"[Storage] Task created successfully in database")

        return task

    def update_task(self, task_id: str, updates: dict) -> Optional[Task]:
        """Update task"""
        task = self.get_task_by_id(task_id)
        if not task:
            return None

        old_status = task.status

        # Update fields
        if "header" in updates:
            task.header = updates["header"]
        if "content" in updates:
            task.content = updates["content"]
        if "status" in updates:
            task.status = updates["status"]
            # Set inProgressAt timestamp when moving to IN_PROGRESS
            if updates["status"] == TaskStatus.IN_PROGRESS and old_status != TaskStatus.IN_PROGRESS:
                task.in_progress_at = datetime.now()
            # Clear inProgressAt when moving out of IN_PROGRESS
            elif updates["status"] != TaskStatus.IN_PROGRESS:
                task.in_progress_at = None
            # Set doneAt timestamp when moving to DONE
            if updates["status"] == TaskStatus.DONE and old_status != TaskStatus.DONE:
                task.done_at = datetime.now()
            # Clear doneAt when moving out of DONE
            elif updates["status"] != TaskStatus.DONE:
                task.done_at = None
        if "priority" in updates:
            task.priority = updates["priority"]
        if "order" in updates:
            task.order = updates["order"]
        if "size" in updates:
            task.size = updates["size"]
        if "eta" in updates:
            if updates["eta"]:
                try:
                    task.eta = datetime.fromisoformat(updates["eta"].replace('Z', '+00:00'))
                except:
                    pass
            else:
                task.eta = None
        if "category" in updates:
            task.category = updates["category"]
        if "returnedFromInProgress" in updates:
            task.returned_from_in_progress = updates["returnedFromInProgress"]
            # Set returnedAt timestamp when marking as returned from in progress
            if updates["returnedFromInProgress"]:
                task.returned_at = datetime.now()
            else:
                task.returned_at = None
        if "inProgressAt" in updates:
            # Allow manual update of inProgressAt (for extending time)
            if updates["inProgressAt"]:
                try:
                    task.in_progress_at = datetime.fromisoformat(updates["inProgressAt"].replace('Z', '+00:00'))
                except:
                    pass
            else:
                task.in_progress_at = None

        # Auto-recalculate order if priority or ETA changed (but not if order was explicitly set by drag)
        if ("priority" in updates or "eta" in updates) and "order" not in updates:
            task.order = calculate_task_order(task)

        # Save to database
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()

        row_data = self._task_to_row(task)
        cursor.execute('''
            UPDATE tasks SET
                header = ?, content = ?, status = ?, priority = ?, size = ?,
                eta = ?, category = ?, created_at = ?, order_num = ?,
                in_progress_at = ?, returned_from_in_progress = ?, done_at = ?, returned_at = ?
            WHERE id = ?
        ''', row_data[1:] + (task_id,))

        conn.commit()
        conn.close()

        return task

    def delete_task(self, task_id: str) -> bool:
        """Delete task"""
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()

        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

    def reorder_tasks(self, task_updates: List[dict]) -> List[Task]:
        """
        Batch update task orders and statuses
        task_updates: [{"id": "xxx", "status": "todo", "order": 0}, ...]
        """
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()

        for update in task_updates:
            task_id = update.get("id")
            if not task_id:
                continue

            # Get current task
            cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
            row = cursor.fetchone()
            if not row:
                continue

            task = self._row_to_task(row)
            old_status = task.status

            # Update status
            if "status" in update:
                task.status = update["status"]
                # Set inProgressAt timestamp when moving to IN_PROGRESS
                if update["status"] == TaskStatus.IN_PROGRESS and old_status != TaskStatus.IN_PROGRESS:
                    task.in_progress_at = datetime.now()
                # Clear inProgressAt when moving out of IN_PROGRESS
                elif update["status"] != TaskStatus.IN_PROGRESS:
                    task.in_progress_at = None
                # Set doneAt timestamp when moving to DONE
                if update["status"] == TaskStatus.DONE and old_status != TaskStatus.DONE:
                    task.done_at = datetime.now()
                # Clear doneAt when moving out of DONE
                elif update["status"] != TaskStatus.DONE:
                    task.done_at = None

            # Update order
            if "order" in update:
                task.order = update["order"]

            # Save to database
            row_data = self._task_to_row(task)
            cursor.execute('''
                UPDATE tasks SET
                    header = ?, content = ?, status = ?, priority = ?, size = ?,
                    eta = ?, category = ?, created_at = ?, order_num = ?,
                    in_progress_at = ?, returned_from_in_progress = ?, done_at = ?, returned_at = ?
                WHERE id = ?
            ''', row_data[1:] + (task_id,))

        conn.commit()
        conn.close()

        return self.get_all_tasks()


# Global storage instance
task_storage = TaskStorage()

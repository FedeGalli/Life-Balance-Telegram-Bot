import json
import os
from datetime import date
from pathlib import Path
from uuid import uuid4


def month_key(value):
    return value.strftime("%Y-%m")


def next_month(value):
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def previous_month(value):
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


def iter_months(start_month, end_month):
    current = date.fromisoformat(start_month + "-01")
    end = date.fromisoformat(end_month + "-01")
    while current <= end:
        yield month_key(current)
        current = next_month(current)


class RecurringExpenseStore:
    """JSON persistence for recurring definitions and per-sheet execution state."""

    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        if not self.path.exists():
            return {"expenses": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Unable to read recurring expenses: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("expenses"), list):
            raise RuntimeError("Recurring expense file has an invalid format.")
        return data

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary_path, self.path)

    def add(self, expense_type, category, amount, description, creator_id, start_month):
        data = self._load()
        expense = {
            "id": uuid4().hex,
            "type": expense_type,
            "category": category,
            "amount": amount,
            "description": description,
            "creator_id": str(creator_id),
            "start_month": start_month,
            "completed_targets": {},
            "notified_months": [],
        }
        data["expenses"].append(expense)
        self._save(data)
        return expense

    def list_for_user(self, user_id, shared_member_ids):
        user_id = str(user_id)
        shared_member_ids = {str(member_id) for member_id in shared_member_ids}
        return [
            expense
            for expense in self._load()["expenses"]
            if expense["creator_id"] == user_id
            or (expense["type"] == "shared" and user_id in shared_member_ids)
        ]

    def all(self):
        return self._load()["expenses"]

    def delete(self, expense_id, user_id, shared_member_ids):
        data = self._load()
        user_id = str(user_id)
        shared_member_ids = {str(member_id) for member_id in shared_member_ids}
        for index, expense in enumerate(data["expenses"]):
            allowed = expense["creator_id"] == user_id or (
                expense["type"] == "shared" and user_id in shared_member_ids
            )
            if expense["id"] == expense_id and allowed:
                removed = data["expenses"].pop(index)
                self._save(data)
                return removed
        return None

    def mark_target_completed(self, expense_id, month, target):
        data = self._load()
        for expense in data["expenses"]:
            if expense["id"] == expense_id:
                targets = expense.setdefault("completed_targets", {}).setdefault(month, [])
                if target not in targets:
                    targets.append(target)
                    self._save(data)
                return
        raise KeyError(f"Recurring expense {expense_id} no longer exists")

    def mark_notified(self, expense_id, month):
        data = self._load()
        for expense in data["expenses"]:
            if expense["id"] == expense_id:
                notified = expense.setdefault("notified_months", [])
                if month not in notified:
                    notified.append(month)
                    self._save(data)
                return
        raise KeyError(f"Recurring expense {expense_id} no longer exists")

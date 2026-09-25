import tempfile
import unittest
from pathlib import Path

from datetime import date

from recurring_expenses import RecurringExpenseStore, iter_months, previous_month


class RecurringExpenseStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = RecurringExpenseStore(
            Path(self.temporary_directory.name) / "recurringExpenses.json"
        )
        self.members = {"alice", "bob"}

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_personal_expense_is_private(self):
        expense = self.store.add(
            "personal", "Rent", "900", "Home", "alice", "2026-10"
        )

        self.assertEqual([expense], self.store.list_for_user("alice", self.members))
        self.assertEqual([], self.store.list_for_user("bob", self.members))
        self.assertIsNone(self.store.delete(expense["id"], "bob", self.members))

    def test_shared_expense_can_be_deleted_by_any_member(self):
        expense = self.store.add(
            "shared", "Bills", "80", "Internet", "alice", "2026-10"
        )

        self.assertEqual([expense], self.store.list_for_user("bob", self.members))
        self.assertEqual(
            expense, self.store.delete(expense["id"], "bob", self.members)
        )

    def test_completion_state_is_idempotent(self):
        expense = self.store.add(
            "personal", "Rent", "900", "Home", "alice", "2026-10"
        )

        self.store.mark_target_completed(expense["id"], "2026-10", "alice")
        self.store.mark_target_completed(expense["id"], "2026-10", "alice")
        self.store.mark_notified(expense["id"], "2026-10")
        self.store.mark_notified(expense["id"], "2026-10")

        saved = self.store.all()[0]
        self.assertEqual(["alice"], saved["completed_targets"]["2026-10"])
        self.assertEqual(["2026-10"], saved["notified_months"])

    def test_iter_months_crosses_year_boundary(self):
        self.assertEqual(
            ["2026-11", "2026-12", "2027-01", "2027-02"],
            list(iter_months("2026-11", "2027-02")),
        )

    def test_previous_month_crosses_year_boundary(self):
        self.assertEqual(date(2025, 12, 1), previous_month(date(2026, 1, 1)))


if __name__ == "__main__":
    unittest.main()

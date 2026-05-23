import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from app.memory import JournalEntry, JournalStore
from app.memory.paths import journal_path, validate_workspace_id


class JournalStoreTest(unittest.TestCase):
    def test_append_entry_creates_daily_markdown_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            day = date(2026, 5, 11)

            path = store.append_entry(
                "local",
                day,
                JournalEntry("tasks", "Create the memory foundation", datetime(2026, 5, 11, 10, 15, tzinfo=timezone.utc)),
            )

            self.assertEqual(path, (Path(tmp) / "local" / "journal" / "2026" / "05" / "2026-05-11.md").resolve())
            content = path.read_text(encoding="utf-8")
            self.assertIn("# 2026-05-11", content)
            self.assertIn("## Tasks", content)
            self.assertIn("- 10:15 Create the memory foundation", content)

    def test_read_missing_day_returns_empty_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = JournalStore(tmp).read_day("local", date(2026, 1, 1))

            self.assertIn("# 2026-01-01", content)
            self.assertIn("## Decisions", content)
            self.assertIn("## Pending", content)

    def test_search_returns_matching_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            day = date(2026, 5, 11)
            store.append_entry("local", day, JournalEntry("decisions", "Use Markdown as source of truth"))

            results = store.search("local", "markdown")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].date, day)
            self.assertIn("Markdown", results[0].line)

    def test_overview_returns_entries_grouped_by_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            day = date(2026, 5, 11)
            store.append_entry("local", day, JournalEntry("tasks", "Build the journal API"))
            store.append_entry("local", day, JournalEntry("decisions", "Keep Markdown as source of truth"))

            overview = store.overview("local", day)

            self.assertEqual(overview.date, day)
            self.assertIn("Build the journal API", overview.sections["tasks"][0])
            self.assertIn("Keep Markdown as source of truth", overview.sections["decisions"][0])
            self.assertEqual(overview.sections["pending"], [])

    def test_timeline_lists_days_newest_first_with_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry("local", date(2026, 5, 10), JournalEntry("tasks", "Older task"))
            store.append_entry("local", date(2026, 5, 11), JournalEntry("tasks", "Newer task"))
            store.append_entry("local", date(2026, 5, 11), JournalEntry("facts", "Newer fact"))

            timeline = store.timeline("local")

            self.assertEqual([item.date for item in timeline], [date(2026, 5, 11), date(2026, 5, 10)])
            self.assertEqual(timeline[0].entry_count, 2)
            self.assertEqual(timeline[0].sections["tasks"], 1)
            self.assertEqual(timeline[0].sections["facts"], 1)

    def test_workspace_id_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            validate_workspace_id("../secret")

    def test_journal_path_uses_controlled_layout(self):
        path = journal_path(Path("/tmp/memory"), "workspace_1", date(2026, 5, 11))

        self.assertEqual(path, Path("/tmp/memory/workspace_1/journal/2026/05/2026-05-11.md"))


if __name__ == "__main__":
    unittest.main()

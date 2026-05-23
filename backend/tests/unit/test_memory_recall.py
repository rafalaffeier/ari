import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from app.memory import JournalEntry, JournalStore
from app.memory.recall import build_memory_context


class MemoryRecallTest(unittest.TestCase):
    current_date = date(2026, 5, 23)

    def test_recall_by_date_cites_daily_journal_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry(
                "local",
                date(2026, 5, 11),
                JournalEntry("decisions", "Keep Markdown as source of truth", datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc)),
            )

            context = build_memory_context(store, "local", "What happened on 2026-05-11?", limit=4)

            self.assertEqual(len(context.sources), 1)
            self.assertEqual(context.sources[0].date, date(2026, 5, 11))
            self.assertEqual(context.sources[0].reason, "date-match")
            self.assertIn("journal/2026/05/2026-05-11.md", context.prompt)
            self.assertIn("Keep Markdown as source of truth", context.prompt)

    def test_recall_by_query_uses_topic_not_whole_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry("local", date(2026, 5, 11), JournalEntry("tasks", "Created API-level memory foundation"))

            context = build_memory_context(store, "local", "When did we discuss API-level?", limit=4)

            self.assertEqual(len(context.sources), 1)
            self.assertEqual(context.sources[0].date, date(2026, 5, 11))
            self.assertEqual(context.sources[0].reason, "text-search")
            self.assertIn("API-level memory foundation", context.prompt)

    def test_recall_by_query_ranks_partial_term_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry("local", date(2026, 5, 10), JournalEntry("tasks", "Reviewed pricing page"))
            store.append_entry("local", date(2026, 5, 11), JournalEntry("decisions", "Launch pricing will stay simple"))
            store.append_entry("local", date(2026, 5, 12), JournalEntry("facts", "Launch checklist reviewed"))

            context = build_memory_context(store, "local", "When did we discuss launch pricing?", limit=2)

            self.assertEqual(len(context.sources), 2)
            self.assertEqual(context.sources[0].date, date(2026, 5, 11))
            self.assertIn("Launch pricing", context.sources[0].line)
            self.assertIn("journal/2026/05/2026-05-11.md", context.prompt)

    def test_empty_non_recall_keeps_prompt_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)

            context = build_memory_context(store, "local", "Help me draft a launch note", limit=4)

            self.assertEqual(context.sources, [])
            self.assertEqual(context.prompt, "")
            self.assertFalse(context.recall_intent)

    def test_empty_recall_adds_no_sources_guardrail(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)

            context = build_memory_context(store, "local", "When did we discuss launch pricing?", limit=4)

            self.assertEqual(context.sources, [])
            self.assertTrue(context.recall_intent)
            self.assertIn("no matching memory sources", context.prompt)
            self.assertIn("do not invent", context.prompt)

    def test_weekly_summary_recall_uses_summary_file_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "local" / "summaries" / "2026-W20.md"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text("# 2026-W20\n\n- Shipped mobile memory MVP.\n- Started AI recall.\n", encoding="utf-8")
            store = JournalStore(tmp)

            context = build_memory_context(store, "local", "What happened in 2026-W20?", limit=4)

            self.assertEqual(len(context.sources), 2)
            self.assertEqual(context.sources[0].reason, "weekly-summary")
            self.assertEqual(context.sources[0].date, date(2026, 5, 11))
            self.assertIn("summaries/2026-W20.md:3", context.prompt)
            self.assertIn("Shipped mobile memory MVP", context.prompt)

    def test_monthly_summary_recall_uses_summary_file_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "local" / "summaries" / "2026-05.md"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text("# 2026-05\n\n- Built encrypted sync foundation.\n", encoding="utf-8")
            store = JournalStore(tmp)

            context = build_memory_context(store, "local", "Summarize 2026-05 memory", limit=4)

            self.assertEqual(len(context.sources), 1)
            self.assertEqual(context.sources[0].reason, "monthly-summary")
            self.assertEqual(context.sources[0].date, date(2026, 5, 1))
            self.assertIn("summaries/2026-05.md:3", context.prompt)
            self.assertIn("encrypted sync foundation", context.prompt)

    def test_today_and_yesterday_recall_use_current_date_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry("local", date(2026, 5, 23), JournalEntry("tasks", "Finished recall endpoint"))
            store.append_entry("local", date(2026, 5, 22), JournalEntry("tasks", "Prepared mobile cache"))

            today = build_memory_context(store, "local", "What happened today?", limit=4, current_date=self.current_date)
            yesterday = build_memory_context(store, "local", "Qué pasó ayer?", limit=4, current_date=self.current_date)

            self.assertEqual(today.sources[0].date, date(2026, 5, 23))
            self.assertIn("Finished recall endpoint", today.prompt)
            self.assertEqual(yesterday.sources[0].date, date(2026, 5, 22))
            self.assertIn("Prepared mobile cache", yesterday.prompt)

    def test_this_week_and_this_month_recall_use_current_date_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            weekly_path = Path(tmp) / "local" / "summaries" / "2026-W21.md"
            monthly_path = Path(tmp) / "local" / "summaries" / "2026-05.md"
            weekly_path.parent.mkdir(parents=True)
            weekly_path.write_text("# 2026-W21\n\n- Closed Phase 6 recall.\n", encoding="utf-8")
            monthly_path.write_text("# 2026-05\n\n- Built mobile MVP and recall.\n", encoding="utf-8")
            store = JournalStore(tmp)

            week = build_memory_context(store, "local", "Resume esta semana", limit=4, current_date=self.current_date)
            month = build_memory_context(store, "local", "Summarize this month", limit=4, current_date=self.current_date)

            self.assertEqual(week.sources[0].source_date, "2026-W21")
            self.assertIn("Closed Phase 6 recall", week.prompt)
            self.assertEqual(month.sources[0].source_date, "2026-05")
            self.assertIn("Built mobile MVP and recall", month.prompt)

    def test_this_week_falls_back_to_journal_days_without_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry("local", date(2026, 5, 18), JournalEntry("tasks", "Opened Phase 6 recall work"))
            store.append_entry("local", date(2026, 5, 23), JournalEntry("decisions", "Keep recall text-only for now"))
            store.append_entry("local", date(2026, 5, 25), JournalEntry("tasks", "Outside the anchor week"))

            context = build_memory_context(store, "local", "What happened this week?", limit=5, current_date=self.current_date)

            self.assertEqual([source.date for source in context.sources], [date(2026, 5, 18), date(2026, 5, 23)])
            self.assertEqual(context.sources[0].reason, "weekly-journal")
            self.assertIn("Opened Phase 6 recall work", context.prompt)
            self.assertNotIn("Outside the anchor week", context.prompt)

    def test_last_month_falls_back_to_journal_days_without_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry("local", date(2026, 4, 5), JournalEntry("tasks", "Prepared sync metadata"))
            store.append_entry("local", date(2026, 5, 5), JournalEntry("tasks", "Current month item"))

            context = build_memory_context(store, "local", "Resumen del mes pasado", limit=5, current_date=self.current_date)

            self.assertEqual(len(context.sources), 1)
            self.assertEqual(context.sources[0].date, date(2026, 4, 5))
            self.assertEqual(context.sources[0].reason, "monthly-journal")
            self.assertIn("Prepared sync metadata", context.prompt)
            self.assertNotIn("Current month item", context.prompt)

    def test_last_n_days_recall_uses_bounded_recent_journal_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry("local", date(2026, 5, 20), JournalEntry("tasks", "Too old for last three days"))
            store.append_entry("local", date(2026, 5, 21), JournalEntry("tasks", "Started recent recall"))
            store.append_entry("local", date(2026, 5, 23), JournalEntry("decisions", "Kept recent recall bounded"))

            context = build_memory_context(store, "local", "What happened in the last 3 days?", limit=5, current_date=self.current_date)

            self.assertEqual([source.date for source in context.sources], [date(2026, 5, 21), date(2026, 5, 23)])
            self.assertEqual(context.sources[0].reason, "recent-journal")
            self.assertIn("Started recent recall", context.prompt)
            self.assertNotIn("Too old", context.prompt)

    def test_recent_recall_defaults_to_last_seven_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JournalStore(tmp)
            store.append_entry("local", date(2026, 5, 16), JournalEntry("tasks", "Older than recent window"))
            store.append_entry("local", date(2026, 5, 17), JournalEntry("tasks", "Opened mobile QA"))

            context = build_memory_context(store, "local", "Qué pasó últimamente?", limit=5, current_date=self.current_date)

            self.assertEqual(len(context.sources), 1)
            self.assertEqual(context.sources[0].date, date(2026, 5, 17))
            self.assertEqual(context.sources[0].reason, "recent-journal")
            self.assertIn("Opened mobile QA", context.prompt)
            self.assertNotIn("Older than recent window", context.prompt)


if __name__ == "__main__":
    unittest.main()

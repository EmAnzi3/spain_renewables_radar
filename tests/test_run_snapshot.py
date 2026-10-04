import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.run_snapshot import load_run_snapshot, save_run_snapshot, snapshot_paths


class RunSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.url = "https://example.invalid/official-index.json"
        self.scope = "12345:2"
        self.now = datetime(2026, 10, 4, 8, tzinfo=timezone.utc)
        self.raw = b'[["original", "source", 3]]'
        self.audit = {
            "source_url": self.url, "complete": True,
            "retrieved_at": self.now.isoformat(),
            "sha256": hashlib.sha256(self.raw).hexdigest(),
            "attempts": [{"http_status": 200}],
        }

    def save(self):
        save_run_snapshot(self.directory, self.scope, self.url, self.raw, self.audit)

    def test_same_run_reuses_exact_bytes_without_redating_evidence(self):
        self.save()
        raw, audit = load_run_snapshot(self.directory, self.scope, self.url, now=self.now+timedelta(minutes=30))
        self.assertEqual(raw, self.raw)
        self.assertEqual(audit["retrieved_at"], self.audit["retrieved_at"])
        self.assertEqual(audit["attempts"], self.audit["attempts"])
        self.assertNotIn("run_snapshot_scope", self.audit)

    def test_other_run_or_attempt_or_source_never_reuses_snapshot(self):
        self.save()
        for scope, url in [("12346:2", self.url), ("12345:3", self.url), (self.scope, self.url+"?other=1"), ("", self.url)]:
            self.assertIsNone(load_run_snapshot(self.directory, scope, url, now=self.now))

    def test_expired_and_future_timestamps_are_not_reused(self):
        self.save()
        for now in [self.now+timedelta(hours=1,seconds=1), self.now-timedelta(seconds=1)]:
            self.assertIsNone(load_run_snapshot(self.directory, self.scope, self.url, now=now))

    def test_corrupt_raw_or_audit_is_a_miss_not_valid_empty_data(self):
        self.save()
        raw_path, audit_path = snapshot_paths(self.directory, self.scope, self.url)
        raw_path.write_bytes(b'<html>maintenance</html>')
        self.assertIsNone(load_run_snapshot(self.directory, self.scope, self.url, now=self.now))
        raw_path.write_bytes(self.raw)
        for data in ["{bad", "[]", json.dumps(dict(self.audit, run_snapshot_scope="foreign")),
                     json.dumps(dict(self.audit, run_snapshot_scope=self.scope, complete=False)),
                     json.dumps(dict(self.audit, run_snapshot_scope=self.scope, retrieved_at="2026-10-04T08:00:00"))]:
            audit_path.write_text(data, encoding="utf-8")
            self.assertIsNone(load_run_snapshot(self.directory, self.scope, self.url, now=self.now))

    def test_incomplete_or_wrong_hash_cannot_be_persisted(self):
        for audit in [dict(self.audit, complete=False), dict(self.audit, sha256="bad"), dict(self.audit, source_url="https://other.invalid/")]:
            with self.assertRaises(ValueError):
                save_run_snapshot(self.directory, self.scope, self.url, self.raw, audit)


if __name__ == "__main__":
    unittest.main()

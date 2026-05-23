import unittest
import tempfile
import uuid
from hashlib import sha256

from fastapi import HTTPException

from app.api.v1.endpoints.sync import (
    _build_encryption_metadata,
    _conflict_path,
    _is_metadata_safe_memory_path,
    _normalize_memory_path,
    _validate_key_wrap_fields,
    _validate_markdown_path,
    _validate_recovery_hint,
)
from app.sync_storage import LocalSyncStorage, checksum_sha256


class SyncMetadataTest(unittest.TestCase):
    def test_normalizes_workspace_relative_path(self):
        self.assertEqual(
            _normalize_memory_path("journal/2026/05/2026-05-23.md"),
            "journal/2026/05/2026-05-23.md",
        )
        self.assertEqual(_normalize_memory_path("journal//today.md"), "journal/today.md")

    def test_rejects_absolute_and_parent_paths(self):
        for path in ("/tmp/memory.md", "../memory.md", "journal/../secret.md", " "):
            with self.subTest(path=path):
                with self.assertRaises(HTTPException):
                    _normalize_memory_path(path)

    def test_validates_markdown_paths(self):
        self.assertEqual(_validate_markdown_path("journal/2026/05/2026-05-23.md"), "journal/2026/05/2026-05-23.md")

        for path in ("journal/today.txt", "notes/readme.markdown", "journal/2026/05/laura-medical.md"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPException):
                    _validate_markdown_path(path)

    def test_builds_markdown_conflict_paths(self):
        md_path = _conflict_path("journal/today.md")

        self.assertTrue(md_path.startswith("journal/today.conflict-"))
        self.assertTrue(md_path.endswith(".md"))

    def test_validates_metadata_safe_memory_paths(self):
        valid_paths = (
            "journal/2026/05/2026-05-23.md",
            "journal/2026/05/2026-05-23.conflict-abcdef123456.md",
            "summaries/2026-W21.md",
            "summaries/2026-05.md",
            "entities/projects.md",
            "entities/people.md",
            "entities/preferences.md",
        )
        for path in valid_paths:
            with self.subTest(path=path):
                self.assertTrue(_is_metadata_safe_memory_path(path))

        invalid_paths = (
            "journal/2026/05/laura-medical.md",
            "summaries/acme-launch.md",
            "entities/rafa.md",
            "notes/readme.md",
        )
        for path in invalid_paths:
            with self.subTest(path=path):
                self.assertFalse(_is_metadata_safe_memory_path(path))

    def test_builds_encryption_metadata(self):
        metadata = _build_encryption_metadata(
            algorithm="aes-256-gcm",
            key_id="workspace-key-v1",
            nonce="abc123456789",
            envelope_version=1,
        )

        self.assertEqual(
            metadata,
            {
                "envelope_version": 1,
                "algorithm": "AES-256-GCM",
                "key_id": "workspace-key-v1",
                "nonce": "abc123456789",
            },
        )

    def test_rejects_invalid_encryption_metadata(self):
        invalid_inputs = (
            {"algorithm": "none", "key_id": "workspace-key-v1", "nonce": "abc123456789", "envelope_version": 1},
            {"algorithm": "AES-256-GCM", "key_id": "bad key", "nonce": "abc123456789", "envelope_version": 1},
            {"algorithm": "AES-256-GCM", "key_id": "workspace-key-v1", "nonce": "short", "envelope_version": 1},
        )
        for kwargs in invalid_inputs:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(HTTPException):
                    _build_encryption_metadata(**kwargs)

    def test_validates_key_wrap_fields(self):
        self.assertEqual(
            _validate_key_wrap_fields(
                "workspace-key-v1",
                "local-test-aes-256-gcm",
                "abcdefghijklmnopqrstuvwxyz123456",
            ),
            (
                "workspace-key-v1",
                "LOCAL-TEST-AES-256-GCM",
                "abcdefghijklmnopqrstuvwxyz123456",
            ),
        )

    def test_rejects_invalid_key_wrap_fields(self):
        invalid_inputs = (
            ("bad key", "LOCAL-TEST-AES-256-GCM", "abcdefghijklmnopqrstuvwxyz123456"),
            ("workspace-key-v1", "none", "abcdefghijklmnopqrstuvwxyz123456"),
            ("workspace-key-v1", "LOCAL-TEST-AES-256-GCM", "short"),
        )
        for args in invalid_inputs:
            with self.subTest(args=args):
                with self.assertRaises(HTTPException):
                    _validate_key_wrap_fields(*args)

    def test_validates_recovery_hint(self):
        self.assertEqual(_validate_recovery_hint("printed recovery kit"), "printed recovery kit")
        self.assertIsNone(_validate_recovery_hint(" "))

        for hint in ("my seed phrase is here", "password: nope", "contraseña guardada"):
            with self.subTest(hint=hint):
                with self.assertRaises(HTTPException):
                    _validate_recovery_hint(hint)

    def test_local_sync_storage_writes_content_outside_postgres(self):
        content = b"# Today\n\n- Synced from desktop.\n"
        workspace_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        file_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        digest = checksum_sha256(content)

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalSyncStorage(tmp)
            key = storage.build_key(workspace_id, file_id, 1, digest)
            storage.write(key, content)

            self.assertEqual(digest, sha256(content).hexdigest())
            self.assertTrue(storage.exists(key))
            self.assertEqual(storage.read(key), content)
            self.assertNotIn(content.decode("utf-8"), key)

    def test_local_sync_storage_rejects_unsafe_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalSyncStorage(tmp)
            for key in ("../secret.md", "workspace//file.md", "workspace/../file.md"):
                with self.subTest(key=key):
                    with self.assertRaises(ValueError):
                        storage.write(key, b"# Nope")


if __name__ == "__main__":
    unittest.main()

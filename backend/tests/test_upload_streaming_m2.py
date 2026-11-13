"""M2 (upload half): uploads are streamed to disk chunk-by-chunk under a byte cap."""
import os
import sys
import hashlib
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.testclient import TestClient


class _PO:
    identity = "po@test"
    sub = "po-1"
    roles = ("process_owner",)
    tenant_id = "tenant_test"
    clearance = "L3"
    actor_type = "human"


class TestUploadStreaming(unittest.TestCase):
    def _client(self):
        from api import routes_ingestion as ri
        app = FastAPI()
        app.include_router(ri.ingestion_router)
        return TestClient(app)

    def _post(self, td, name, payload, max_bytes, owner_calls=None):
        def _record(tenant_id, filename, identity, sha256=None):
            if owner_calls is not None:
                owner_calls.append((filename, sha256))

        with patch("api.routes_ingestion.authenticate_request", return_value=_PO()), \
             patch("api.routes_ingestion.get_max_file_size_bytes", return_value=max_bytes), \
             patch("api.routes_ingestion.get_max_file_size_mb", return_value=max_bytes / (1024 * 1024)), \
             patch("api.routes_ingestion.tenant_uploads_dir", return_value=td), \
             patch("api.routes_ingestion.record_upload_owner", side_effect=_record):
            return self._client().post(
                "/api/uploads/upload",
                files={"file": (name, payload, "text/plain")},
            )

    def test_multi_chunk_upload_is_saved_intact_with_matching_sha(self):
        # 200 KB spans several 64 KB chunks.
        payload = (b"Step 1. Restart the print spooler service.\n" * 5000)[:200_000]
        calls = []
        with tempfile.TemporaryDirectory() as td:
            r = self._post(td, "sop.txt", payload, max_bytes=1024 * 1024, owner_calls=calls)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["size_bytes"], len(payload))
            self.assertEqual(os.listdir(td), ["sop.txt"])  # no .part left behind
            with open(os.path.join(td, "sop.txt"), "rb") as f:
                self.assertEqual(f.read(), payload)
        self.assertEqual(calls, [("sop.txt", hashlib.sha256(payload).hexdigest())])

    def test_oversized_upload_leaves_no_file_and_no_temp_file(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            r = self._post(td, "big.txt", b"X" * 300_000, max_bytes=100_000, owner_calls=calls)
            self.assertEqual(r.status_code, 400)
            self.assertEqual(os.listdir(td), [])
        self.assertEqual(calls, [])

    def test_oversized_upload_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            existing = os.path.join(td, "sop.txt")
            with open(existing, "wb") as f:
                f.write(b"original approved content")
            r = self._post(td, "sop.txt", b"X" * 300_000, max_bytes=100_000)
            self.assertEqual(r.status_code, 400)
            self.assertEqual(os.listdir(td), ["sop.txt"])
            with open(existing, "rb") as f:
                self.assertEqual(f.read(), b"original approved content")

    def test_upload_goes_through_temp_file_then_atomic_rename(self):
        # Proves the streaming path: the bytes land in a .part temp file first
        # and only an atomic rename puts them at the real name.
        from api import routes_ingestion as ri
        real_replace = os.replace
        seen = []

        def _spy(src, dst):
            seen.append((os.path.basename(src), os.path.basename(dst), os.path.getsize(src)))
            return real_replace(src, dst)

        payload = b"B" * 200_000
        with tempfile.TemporaryDirectory() as td:
            with patch.object(ri.os, "replace", side_effect=_spy):
                r = self._post(td, "sop.txt", payload, max_bytes=1024 * 1024)
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(seen), 1)
        src, dst, size = seen[0]
        self.assertTrue(src.endswith(".part"), src)
        self.assertEqual(dst, "sop.txt")
        self.assertEqual(size, len(payload))

    def test_failure_before_rename_keeps_existing_file_and_cleans_temp(self):
        # If the upload dies before the final rename, the previously uploaded
        # file must be untouched and no temp file may be left behind.
        from api import routes_ingestion as ri
        with tempfile.TemporaryDirectory() as td:
            existing = os.path.join(td, "sop.txt")
            with open(existing, "wb") as f:
                f.write(b"original approved content")
            with patch.object(ri.os, "replace", side_effect=OSError("disk error")):
                r = self._post(td, "sop.txt", b"NEW" * 50_000, max_bytes=1024 * 1024)
            self.assertEqual(r.status_code, 500)
            self.assertEqual(os.listdir(td), ["sop.txt"])
            with open(existing, "rb") as f:
                self.assertEqual(f.read(), b"original approved content")

    def test_exactly_at_limit_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            r = self._post(td, "edge.txt", b"A" * 100_000, max_bytes=100_000)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(os.path.getsize(os.path.join(td, "edge.txt")), 100_000)


if __name__ == "__main__":
    unittest.main()

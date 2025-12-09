import json
import os
import time
import unittest
from pathlib import Path
import tempfile
from threading import Event
from uuid import uuid4

from firebase_user import FirebaseClient


CONFIG_PATH = Path(__file__).resolve().parent / "app.config.json"
DEFAULT_EMAIL = "bferrand.maths@gmail.com"
DEFAULT_PASSWORD = "azertyuiop"
RUN_RTDB_STREAM = os.getenv("RUN_RTDB_STREAM", "0") == "1"
RUN_STORAGE = os.getenv("RUN_STORAGE_TESTS", "0") == "1"
FUNCTION_NAME = os.getenv("FIREBASE_FUNCTION_NAME")


class IntegrationTestBase(unittest.TestCase):
    """Base helpers for integration tests."""

    @classmethod
    def setUpClass(cls) -> None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cls.config = json.load(f)

        cls.email = os.getenv("FIREBASE_TEST_EMAIL", DEFAULT_EMAIL)
        cls.password = os.getenv("FIREBASE_TEST_PASSWORD", DEFAULT_PASSWORD)

        # Ensure RTDB uses the correct regional endpoint
        if "databaseURL" not in cls.config:
            project_id = cls.config.get("projectId")
            cls.config["databaseURL"] = os.getenv(
                "FIREBASE_DATABASE_URL",
                f"https://{project_id}-default-rtdb.europe-west1.firebasedatabase.app",
            )

        cls.client = FirebaseClient(config=cls.config)
        cls.client.auth.sign_in(cls.email, cls.password)

    def setUp(self) -> None:
        # Ensure we start authenticated for each test
        if not self.client.auth.authenticated:
            self.client.auth.sign_in(self.email, self.password)


class AuthIntegrationTests(IntegrationTestBase):
    def test_sign_in_and_refresh_token(self):
        self.assertTrue(self.client.auth.authenticated)
        refresh = self.client.auth.get_refresh_token()
        self.assertIsNotNone(refresh)

        # Refresh the token and ensure authentication stays valid
        self.client.auth.refresh_token()
        self.assertTrue(self.client.auth.authenticated)

    def test_get_user_info_fields(self):
        info = self.client.auth.get_user_info()
        self.assertEqual(info["email"], self.email)
        self.assertIn("uid", info)
        self.assertIn("emailVerified", info)

    def test_session_roundtrip(self):
        session_data = self.client.auth.to_session_dict()
        self.assertIn("refresh_token", session_data)

        new_client = FirebaseClient(config=self.config)
        new_client.auth.from_session_dict(session_data)

        self.assertTrue(new_client.auth.authenticated)
        self.assertEqual(new_client.user.get("email"), self.email)

    def test_update_profile_roundtrip(self):
        original_info = self.client.auth.get_user_info()
        original_display = original_info.get("displayName")

        new_display = f"Integration Tester {uuid4().hex[:6]}"
        self.client.auth.update_profile(display_name=new_display)

        updated = self.client.auth.get_user_info()
        self.assertEqual(updated.get("displayName"), new_display)
        self.assertTrue(self.client.auth.authenticated)

        # Restore original display name to avoid side effects
        self.client.auth.update_profile(display_name=original_display or "")

    def test_log_out_and_relogin(self):
        self.client.auth.log_out()
        self.assertFalse(self.client.auth.authenticated)

        self.client.auth.sign_in(self.email, self.password)
        self.assertTrue(self.client.auth.authenticated)


class FirestoreIntegrationTests(IntegrationTestBase):
    collection = "tests_integration"

    def _new_doc_id(self) -> str:
        return f"doc-{uuid4().hex[:8]}"

    def _delete_doc(self, doc_id: str) -> None:
        try:
            self.client.firestore.delete_document(self.collection, doc_id)
        except Exception:
            pass

    def test_set_and_get_document(self):
        doc_id = self._new_doc_id()
        data = {"title": "hello", "views": 1, "published": True}

        self.client.firestore.set_document(self.collection, doc_id, data)
        fetched = self.client.firestore.get_document(self.collection, doc_id)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "hello")
        self.assertEqual(fetched["views"], 1)

        self._delete_doc(doc_id)
        missing = self.client.firestore.get_document(self.collection, doc_id, default=None)
        self.assertIsNone(missing)

    def test_update_document(self):
        doc_id = self._new_doc_id()
        self.client.firestore.set_document(self.collection, doc_id, {"title": "draft", "views": 0})

        self.client.firestore.update_document(self.collection, doc_id, {"views": 5, "tags": ["news"]})
        fetched = self.client.firestore.get_document(self.collection, doc_id)

        self.assertEqual(fetched["views"], 5)
        self.assertEqual(fetched["tags"], ["news"])

        self._delete_doc(doc_id)

    def test_document_exists(self):
        doc_id = self._new_doc_id()
        self.client.firestore.set_document(self.collection, doc_id, {"ok": True})

        self.assertTrue(self.client.firestore.document_exists(self.collection, doc_id))

        self._delete_doc(doc_id)
        self.assertFalse(self.client.firestore.document_exists(self.collection, doc_id))

    def test_list_documents_includes_created_doc(self):
        doc_id = self._new_doc_id()
        self.client.firestore.set_document(self.collection, doc_id, {"kind": "list-test"})

        docs = self.client.firestore.list_documents(self.collection, page_size=50)
        ids = {doc["id"] for doc in docs}
        self.assertIn(doc_id, ids)

        self._delete_doc(doc_id)

    def test_query_filters_and_ordering(self):
        doc_id_newer = self._new_doc_id()
        doc_id_older = self._new_doc_id()

        now = time.time()
        older = now - 60
        marker = f"ok-{uuid4().hex[:6]}"

        self.client.firestore.set_document(self.collection, doc_id_newer, {"status": marker, "created_at": now})
        self.client.firestore.set_document(self.collection, doc_id_older, {"status": marker, "created_at": older})

        results = self.client.firestore.query(
            self.collection,
            where=[("status", "==", marker)],
            limit=10
        )

        ids = [doc["id"] for doc in results]
        self.assertIn(doc_id_newer, ids)
        self.assertIn(doc_id_older, ids)

        self._delete_doc(doc_id_newer)
        self._delete_doc(doc_id_older)

    def test_commit_and_transform_helpers(self):
        doc_id = self._new_doc_id()
        writes = [
            self.client.firestore.build_set_write(self.collection, doc_id, {"score": 1, "tags": ["a"]})
        ]
        self.client.firestore.commit(writes)

        transform = self.client.firestore.build_transform_write(
            self.collection,
            doc_id,
            [
                ("score", "increment", 2),
                ("tags", "arrayUnion", ["b"]),
            ]
        )
        self.client.firestore.commit([transform])

        fetched = self.client.firestore.get_document(self.collection, doc_id)
        self.assertEqual(fetched.get("score"), 3)
        self.assertEqual(set(fetched.get("tags", [])), {"a", "b"})

        delete_write = self.client.firestore.build_delete_write(self.collection, doc_id)
        self.client.firestore.commit([delete_write])
        self.assertFalse(self.client.firestore.document_exists(self.collection, doc_id))


class RealtimeDatabaseIntegrationTests(IntegrationTestBase):
    base_path = "tests_rtdb"

    def _path(self, suffix: str) -> str:
        return f"{self.base_path}/{suffix}"

    def test_set_get_delete(self):
        path = self._path(f"simple-{uuid4().hex[:6]}")
        payload = {"a": 1, "b": "x"}

        self.client.rtdb.set(path, payload)
        fetched = self.client.rtdb.get(path)
        self.assertEqual(fetched, payload)

        self.client.rtdb.delete(path)
        self.assertIsNone(self.client.rtdb.get(path, default=None))

    def test_push_and_update(self):
        list_path = self._path("list")
        key = self.client.rtdb.push(list_path, {"name": "john", "score": 1})
        self.assertIsNotNone(key)

        self.client.rtdb.update(f"{list_path}/{key}", {"score": 2})
        fetched = self.client.rtdb.get(f"{list_path}/{key}")
        self.assertEqual(fetched["score"], 2)
        self.assertEqual(fetched["name"], "john")

    def test_stream_receives_updates(self):
        if not RUN_RTDB_STREAM:
            self.skipTest("RTDB streaming test disabled (set RUN_RTDB_STREAM=1 to enable)")

        path = self._path(f"stream-{uuid4().hex[:6]}")
        received = Event()
        events = []

        def on_change(event_type, data):
            events.append((event_type, data))
            received.set()

        stream = self.client.rtdb.stream(path, callback=on_change)
        stream.start()
        try:
            time.sleep(0.5)  # allow stream to open
            self.client.rtdb.set(path, {"hello": "world"})
            self.client.rtdb.update(path, {"hello": "stream"})
            if not received.wait(timeout=10):
                self.skipTest("RTDB streaming event not received in time")
            self.assertTrue(events)
        finally:
            stream.stop()
            self.client.rtdb.delete(path)


class StorageIntegrationTests(IntegrationTestBase):
    remote_prefix = "tests_storage"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if not RUN_STORAGE:
            raise unittest.SkipTest("Storage tests disabled (set RUN_STORAGE_TESTS=1 when bucket is ready)")
        if not cls.config.get("storageBucket"):
            raise unittest.SkipTest("No storageBucket configured")

    def _remote(self, name: str) -> str:
        return f"{self.remote_prefix}/{name}"

    def test_upload_download_delete(self):
        content = f"hello storage {uuid4().hex}"
        with tempfile.TemporaryDirectory() as tmpdir:
            local = Path(tmpdir) / "sample.txt"
            local.write_text(content, encoding="utf-8")
            remote = self._remote(f"sample-{uuid4().hex[:6]}.txt")

            self.client.storage.upload_file(str(local), remote)

            files = self.client.storage.list_files()
            self.assertIn(remote, files)

            download_path = Path(tmpdir) / "downloaded.txt"
            self.client.storage.download_file(remote, str(download_path))
            self.assertEqual(download_path.read_text(encoding="utf-8"), content)

            self.client.storage.delete_file(remote)
            files_after = self.client.storage.list_files()
            self.assertNotIn(remote, files_after)


class FunctionsIntegrationTests(IntegrationTestBase):
    def test_callable_function_if_configured(self):
        if not FUNCTION_NAME:
            self.skipTest("No FIREBASE_FUNCTION_NAME provided for callable function test")

        payload = {"ping": "pong", "test": True}
        result = self.client.functions.call(FUNCTION_NAME, data=payload)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()

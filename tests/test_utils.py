import base64
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unittest

from firebase_user.utils import (
    convert_in,
    convert_out,
    to_typed_dict,
    has_changed,
    is_newer,
    list_files,
)


class ConvertTests(unittest.TestCase):
    def test_integer_is_string_encoded(self):
        payload = convert_in(123)
        self.assertEqual(payload, {"integerValue": "123"})

    def test_timestamp_roundtrip(self):
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        encoded = convert_in(now)
        self.assertIn("timestampValue", encoded)
        decoded = convert_out(encoded)
        self.assertIsInstance(decoded, datetime)
        self.assertEqual(decoded.replace(tzinfo=timezone.utc), now)

    def test_bytes_roundtrip(self):
        data = b"hello"
        encoded = convert_in(data)
        self.assertIn("bytesValue", encoded)
        decoded = convert_out(encoded)
        self.assertEqual(decoded, data)

    def test_map_array_roundtrip(self):
        payload = {"name": "john", "scores": [1, 2, 3], "active": True}
        encoded = to_typed_dict(payload)
        decoded = {k: convert_out(v) for k, v in encoded["fields"].items()}
        self.assertEqual(decoded, payload)


class FileHelpersTests(unittest.TestCase):
    def test_list_files_and_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            file_a = root / "a.txt"
            file_a.write_text("hello")
            details = list_files(tmpdir)
            self.assertIn("a.txt", details)
            # md5 of "hello"
            expected_md5 = base64.b16encode(__import__("hashlib").md5(b"hello").digest()).decode().lower()
            self.assertEqual(details["a.txt"]["md5Hash"], expected_md5)

    def test_has_changed_and_is_newer(self):
        now = datetime.now(timezone.utc)
        older = (now - timedelta(seconds=60)).isoformat()
        newer = now.isoformat()
        f1 = {"size": 10, "md5Hash": "abc", "updated": older}
        f2 = {"size": 10, "md5Hash": "def", "updated": newer}
        self.assertTrue(has_changed(f1, f2))
        self.assertTrue(is_newer(f2, f1))
        self.assertFalse(is_newer(f1, f2))


if __name__ == "__main__":
    unittest.main()

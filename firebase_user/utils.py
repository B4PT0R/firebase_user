"""Utility functions for Firebase client."""

import base64
import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def convert_path_to_prefix(path: str) -> str:
    """Convert filesystem path to Firebase Storage prefix (always forward slashes)."""
    return Path(path).as_posix()


def convert_prefix_to_path(prefix: str) -> str:
    """Convert Firebase Storage prefix to filesystem path."""
    return str(Path(prefix))


def list_files(directory: str) -> Dict[str, Dict[str, Any]]:
    """
    List all file paths, relative to the given directory, in the directory and its subdirectories,
    along with details like size, MIME type, last modified time in ISO 8601 format, and MD5 hash.

    :param directory: The root directory to walk through.
    :return: A dict with relative paths as keys and file details as values.
    """
    dir_path = Path(directory)
    file_details = {}

    for file_path in dir_path.rglob('*'):
        if file_path.is_file():
            # Get relative path
            relative_path = file_path.relative_to(dir_path)
            # Get file details
            stat_info = file_path.stat()
            mime_type, _ = mimetypes.guess_type(str(file_path))
            updated_time = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc).isoformat()  # ISO 8601 format

            # Calculate MD5 hash
            md5_hash = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5_hash.update(chunk)

            file_details[str(relative_path)] = {
                'size': stat_info.st_size,
                'type': mime_type if mime_type else 'Unknown',
                'updated': updated_time,
                'md5Hash': md5_hash.hexdigest()
            }

    return file_details


def has_changed(file1: Dict[str, Any], file2: Dict[str, Any]) -> bool:
    """
    Compare two files to determine if they are different.
    Uses MD5 hash if available, otherwise falls back to size comparison.

    :param file1: Details of the first file.
    :param file2: Details of the second file.
    :return: True if files are different, False if identical.
    """
    # Compare MD5 hashes if available (most reliable)
    hash1 = file1.get('md5Hash')
    hash2 = file2.get('md5Hash')
    if hash1 and hash2:
        return hash1 != hash2

    # Fallback: compare size if hash not available
    return file1.get('size') != file2.get('size')


def is_newer(file1: Dict[str, Any], file2: Dict[str, Any]) -> bool:
    """
    Determine if file1 is newer than file2 based on modification timestamp.

    :param file1: Details of the first file.
    :param file2: Details of the second file.
    :return: True if file1 is newer than file2, False otherwise.
    """
    file1_updated = datetime.fromisoformat(file1['updated'].rstrip('Z'))
    file2_updated = datetime.fromisoformat(file2['updated'].rstrip('Z'))
    return file1_updated > file2_updated


def convert_in(value: Any) -> Dict[str, Any]:
    """Convert Python value to Firestore typed value."""
    if isinstance(value, str):
        return {'stringValue': value}
    if isinstance(value, bool):
        return {'booleanValue': value}
    if isinstance(value, int):
        return {'integerValue': str(value)}
    if isinstance(value, float):
        return {'doubleValue': value}
    if isinstance(value, datetime):
        iso_value = value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        return {'timestampValue': iso_value}
    if isinstance(value, (bytes, bytearray)):
        b64 = base64.b64encode(bytes(value)).decode('ascii')
        return {'bytesValue': b64}
    if isinstance(value, dict):
        return {'mapValue': {'fields': {k: convert_in(v) for k, v in value.items()}}}
    if isinstance(value, list):
        return {'arrayValue': {'values': [convert_in(v) for v in value]}}
    return {'nullValue': None}


def to_typed_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dictionary to Firestore typed fields."""
    return {'fields': {k: convert_in(v) for k, v in data.items()}}


def convert_out(value: Dict[str, Any]) -> Any:
    """Convert Firestore typed value to Python value."""
    if 'nullValue' in value:
        return None
    if 'stringValue' in value:
        return value['stringValue']
    if 'booleanValue' in value:
        return value['booleanValue']
    if 'integerValue' in value:
        return int(value['integerValue'])
    if 'doubleValue' in value:
        return float(value['doubleValue'])
    if 'timestampValue' in value:
        ts = value['timestampValue']
        # Normalise Z to +00:00 for fromisoformat
        ts = ts.replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return value['timestampValue']
    if 'bytesValue' in value:
        try:
            return base64.b64decode(value['bytesValue'])
        except Exception:
            return value['bytesValue']
    if 'geoPointValue' in value:
        return value['geoPointValue']  # Returns a dict with 'latitude' and 'longitude'
    if 'referenceValue' in value:
        return value['referenceValue']  # Firestore document reference
    if 'mapValue' in value:
        content = value['mapValue'].get('fields', {})
        return {key: convert_out(val) for key, val in content.items()}
    if 'arrayValue' in value:
        content = value['arrayValue'].get('values', [])
        return [convert_out(item) for item in content]
    return None  # Add additional cases as needed


def to_dict(document: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a Firestore document with type annotations to a regular dictionary.
    """
    if 'fields' in document:
        return {key: convert_out(value) for key, value in document['fields'].items()}
    else:
        return {}

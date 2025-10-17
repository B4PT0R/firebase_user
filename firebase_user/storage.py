"""Storage module for Firebase client."""

import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Any

from .utils import list_files, has_changed, is_newer, convert_path_to_prefix, convert_prefix_to_path

if TYPE_CHECKING:
    from .client import FirebaseClient


class Storage:
    """Handle Firebase Storage operations."""

    def __init__(self, client: 'FirebaseClient'):
        self.client = client
        self.base_url = f"https://firebasestorage.googleapis.com/v0/b/{self.client.config['storageBucket']}/o/"

    def _get_user_prefix(self) -> str:
        """Get the authenticated user's storage prefix."""
        if not self.client.user or not self.client.user.get('email'):
            raise ValueError("No authenticated user.")
        return f"{self.client.user['email']}/"

    def _normalize_remote_path(self, path: str) -> str:
        """Normalize remote path: convert to POSIX and remove leading slashes."""
        return Path(path).as_posix().lstrip('/')

    def encode_path(self, path: str) -> str:
        """URL-encode the path."""
        return urllib.parse.quote(path, safe='')

    def list_files(self) -> Dict[str, Dict[str, Any]]:
        """List files in the user's storage directory with additional metadata."""
        user_prefix = self._get_user_prefix()
        encoded_path = self.encode_path(user_prefix)
        request_url = self.base_url + "?prefix=" + encoded_path

        headers = {'Authorization': "Bearer {token}"}
        response = self.client._make_request(type='get', url=request_url, headers=headers)

        files = {}
        # Use metadata directly from list response (no need for extra requests)
        for item in response.json().get('items', []):
            relative_prefix = item['name'].removeprefix(user_prefix)
            name = convert_prefix_to_path(relative_prefix)
            files[name] = {
                'size': int(item.get('size', 0)),
                'type': item.get('contentType', 'Unknown'),
                'updated': item.get('updated', 'Unknown'),
                'md5Hash': item.get('md5Hash', '')
            }
        return files

    def delete_file(self, file_name: str) -> None:
        """Delete a file from Firebase Storage."""
        user_prefix = self._get_user_prefix()
        normalized_path = self._normalize_remote_path(file_name)
        encoded_path = self.encode_path(user_prefix + normalized_path)
        request_url = self.base_url + encoded_path
        headers = {'Authorization': "Bearer {token}"}
        self.client._make_request(type='delete', url=request_url, headers=headers)
        if self.client.verbose:
            print(f"Successfully deleted {file_name}")

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from Firebase Storage."""
        user_prefix = self._get_user_prefix()
        normalized_path = self._normalize_remote_path(remote_path)
        encoded_path = self.encode_path(user_prefix + normalized_path)
        request_url = self.base_url + encoded_path + "?alt=media"
        headers = {'Authorization': "Bearer {token}"}
        response = self.client._make_request(type='get', url=request_url, headers=headers, stream=True)

        local_file = Path(local_path)
        local_file.parent.mkdir(parents=True, exist_ok=True)
        with open(local_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if self.client.verbose:
            print(f"Successfully downloaded user_storage/{remote_path} to {local_file.absolute()}")

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a file to Firebase Storage."""
        local_file = Path(local_path)
        if not local_file.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        if not local_file.is_file():
            raise ValueError(f"Path is not a file: {local_path}")

        user_prefix = self._get_user_prefix()
        normalized_path = self._normalize_remote_path(remote_path)
        encoded_path = self.encode_path(user_prefix + normalized_path)
        request_url = self.base_url + encoded_path
        headers = {'Authorization': "Bearer {token}"}
        with open(local_file, 'rb') as f:
            files = {'file': f}
            self.client._make_request(type='post', url=request_url, headers=headers, files=files)
        if self.client.verbose:
            print(f"Successfully uploaded {local_file.absolute()} to user_storage/{remote_path}")

    def dump_folder(self, local_folder: str) -> None:
        """
        Synchronizes the local folder to Firebase Storage.
        - Uploads newer files to Storage.
        - Deletes files from Storage that don't exist locally.
        """
        local_dir = Path(local_folder)
        if not local_dir.is_dir():
            raise FileNotFoundError(f"Cannot dump a folder if it does not exist: {local_folder}")

        lfiles = list_files(str(local_dir))
        sfiles = self.list_files()

        # Handle uploads
        for file in lfiles:
            if file not in sfiles:
                # File only exists locally, upload it
                self.upload_file(str(local_dir / file), convert_path_to_prefix(file))
            elif has_changed(lfiles[file], sfiles[file]) and is_newer(lfiles[file], sfiles[file]):
                # File exists in both but local is newer, upload it
                self.upload_file(str(local_dir / file), convert_path_to_prefix(file))

        # Handle deletions
        for file in sfiles:
            if file not in lfiles:
                self.delete_file(convert_path_to_prefix(file))

    def load_folder(self, local_folder: str) -> None:
        """
        Synchronizes Firebase Storage to the local folder.
        - Downloads newer files from Storage.
        - Deletes local files that don't exist in Storage.
        (Beware that this will overwrite/delete files in the chosen local folder, use with caution.)
        """
        local_dir = Path(local_folder).absolute()
        lfiles = list_files(str(local_dir)) if local_dir.is_dir() else {}
        sfiles = self.list_files()

        # Handle downloads
        for file in sfiles:
            if file not in lfiles:
                # File only exists remotely, download it
                self.download_file(convert_path_to_prefix(file), str(local_dir / file))
            elif has_changed(sfiles[file], lfiles[file]) and is_newer(sfiles[file], lfiles[file]):
                # File exists in both but remote is newer, download it
                self.download_file(convert_path_to_prefix(file), str(local_dir / file))

        # Handle deletions
        for file in lfiles:
            local_file = local_dir / file
            if file not in sfiles:
                local_file.unlink()
                if self.client.verbose:
                    print(f"Deleted {local_file}")
                # Remove empty parent directories
                parent = local_file.parent
                while parent != local_dir and not any(parent.iterdir()):
                    parent.rmdir()
                    if self.client.verbose:
                        print(f"Deleted {parent}")
                    parent = parent.parent

    def sync_folder(self, local_folder: str) -> None:
        """
        Bidirectional sync: merge local and remote folders.
        - Files only in one location are copied to the other
        - Files in both locations: newer file (timestamp) wins if content differs (MD5)
        - No deletions - only adds and updates

        :param local_folder: Local folder path to sync
        """
        local_dir = Path(local_folder).absolute()

        # Create local folder if it doesn't exist
        if not local_dir.exists():
            local_dir.mkdir(parents=True, exist_ok=True)

        lfiles = list_files(str(local_dir)) if local_dir.is_dir() else {}
        sfiles = self.list_files()

        # Track stats for verbose output
        uploaded = 0
        downloaded = 0
        skipped = 0

        # Handle files only in local (upload them)
        for file in lfiles:
            if file not in sfiles:
                self.upload_file(str(local_dir / file), convert_path_to_prefix(file))
                uploaded += 1

        # Handle files only in remote (download them)
        for file in sfiles:
            if file not in lfiles:
                self.download_file(convert_path_to_prefix(file), str(local_dir / file))
                downloaded += 1

        # Handle files in both locations
        for file in lfiles:
            if file in sfiles:
                if has_changed(lfiles[file], sfiles[file]):
                    # Files are different, use the newer one
                    if is_newer(lfiles[file], sfiles[file]):
                        # Local is newer, upload
                        self.upload_file(str(local_dir / file), convert_path_to_prefix(file))
                        uploaded += 1
                    else:
                        # Remote is newer, download
                        self.download_file(convert_path_to_prefix(file), str(local_dir / file))
                        downloaded += 1
                else:
                    # Files are identical (same MD5), skip
                    skipped += 1

        if self.client.verbose:
            print(f"Sync complete: {uploaded} uploaded, {downloaded} downloaded, {skipped} skipped")

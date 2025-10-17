"""Realtime Database module for Firebase client."""

import json
import requests
from typing import TYPE_CHECKING, Dict, Any, Optional, Callable
from threading import Thread
import sseclient  # Will need to add dependency

from .exceptions import FirebaseException

if TYPE_CHECKING:
    from .client import FirebaseClient


class RealtimeDatabase:
    """Handle Firebase Realtime Database operations."""

    def __init__(self, client: 'FirebaseClient'):
        self.client = client
        # Get database URL from config
        db_url = client.config.get('databaseURL')
        if not db_url:
            # Construct from projectId if not provided
            project_id = client.config.get('projectId')
            if project_id:
                db_url = f"https://{project_id}-default-rtdb.firebaseio.com"
            else:
                raise ValueError("Cannot determine Realtime Database URL")

        self.base_url = db_url.rstrip('/')

    def _build_url(self, path: str) -> str:
        """Build full URL with path and .json extension."""
        path = path.strip('/')
        url = f"{self.base_url}/{path}.json" if path else f"{self.base_url}/.json"

        # Add auth parameter if user is authenticated
        if self.client.user and self.client.user.get('idToken'):
            url += f"?auth={self.client.user['idToken']}"

        return url

    def get(self, path: str = '', default: Any = None) -> Any:
        """
        Read data from Realtime Database.

        :param path: Database path (e.g., 'users/john' or 'messages')
        :param default: Value to return if path doesn't exist
        :return: Data at the specified path
        """
        url = self._build_url(path)
        headers = {'Accept': 'application/json'}

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            if data is None:
                return default
            if self.client.verbose:
                print(f"Data retrieved from {path}")
            return data
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return default
            raise FirebaseException(f"Realtime Database error: {e}")

    def set(self, path: str, data: Any) -> None:
        """
        Write/replace data at a path (overwrites existing data).

        :param path: Database path
        :param data: Data to write (will be JSON serialized)
        """
        url = self._build_url(path)
        headers = {'Content-Type': 'application/json'}

        response = requests.put(url, headers=headers, json=data)
        response.raise_for_status()

        if self.client.verbose:
            print(f"Data set at {path}")

    def push(self, path: str, data: Any) -> str:
        """
        Add data with auto-generated key (like a list append).

        :param path: Database path
        :param data: Data to push
        :return: The auto-generated key
        """
        url = self._build_url(path)
        headers = {'Content-Type': 'application/json'}

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()

        result = response.json()
        key = result.get('name')

        if self.client.verbose:
            print(f"Data pushed to {path} with key {key}")

        return key

    def update(self, path: str, data: Dict[str, Any]) -> None:
        """
        Update specific fields without overwriting other data.

        :param path: Database path
        :param data: Dictionary of fields to update
        """
        url = self._build_url(path)
        headers = {'Content-Type': 'application/json'}

        response = requests.patch(url, headers=headers, json=data)
        response.raise_for_status()

        if self.client.verbose:
            print(f"Data updated at {path}")

    def delete(self, path: str) -> None:
        """
        Delete data at a path.

        :param path: Database path to delete
        """
        url = self._build_url(path)

        response = requests.delete(url)
        response.raise_for_status()

        if self.client.verbose:
            print(f"Data deleted at {path}")

    def stream(
        self,
        path: str,
        callback: Callable[[str, Any], None],
        error_callback: Optional[Callable[[Exception], None]] = None
    ) -> 'StreamListener':
        """
        Stream real-time updates from a path using Server-Sent Events.

        :param path: Database path to stream
        :param callback: Function called on data changes: callback(event_type, data)
                        event_type can be: 'put', 'patch', 'keep-alive', 'cancel', 'auth_revoked'
        :param error_callback: Optional function called on errors
        :return: StreamListener object to control the stream
        """
        return StreamListener(self, path, callback, error_callback)


class StreamListener:
    """Handle Server-Sent Events streaming for Realtime Database."""

    def __init__(
        self,
        rtdb: RealtimeDatabase,
        path: str,
        callback: Callable[[str, Any], None],
        error_callback: Optional[Callable[[Exception], None]] = None
    ):
        self.rtdb = rtdb
        self.path = path
        self.callback = callback
        self.error_callback = error_callback
        self.thread: Optional[Thread] = None
        self.running = False

    def _stream_loop(self):
        """Main streaming loop running in thread."""
        url = self.rtdb._build_url(self.path)

        # SSE requires specific headers
        headers = {
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache'
        }

        try:
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()

            client = sseclient.SSEClient(response)

            for event in client.events():
                if not self.running:
                    break

                event_type = event.event
                data = json.loads(event.data) if event.data else None

                # Handle different event types
                if event_type in ('put', 'patch'):
                    self.callback(event_type, data)
                elif event_type == 'keep-alive':
                    # Heartbeat to keep connection alive
                    if self.rtdb.client.verbose:
                        print("Keep-alive received")
                elif event_type in ('cancel', 'auth_revoked'):
                    if self.rtdb.client.verbose:
                        print(f"Stream {event_type}")
                    break

        except Exception as e:
            if self.error_callback:
                self.error_callback(e)
            elif self.rtdb.client.verbose:
                print(f"Stream error: {e}")

    def start(self) -> None:
        """Start streaming in background thread."""
        if self.running:
            return

        self.running = True
        self.thread = Thread(target=self._stream_loop, daemon=True)
        self.thread.start()

        if self.rtdb.client.verbose:
            print(f"Started streaming {self.path}")

    def stop(self) -> None:
        """Stop streaming."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
            self.thread = None

        if self.rtdb.client.verbose:
            print(f"Stopped streaming {self.path}")

    @property
    def is_streaming(self) -> bool:
        """Check if currently streaming."""
        return self.running

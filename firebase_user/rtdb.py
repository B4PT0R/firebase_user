"""Realtime Database module for Firebase client."""

import json
import time
import requests
from urllib.parse import urlencode
from typing import TYPE_CHECKING, Dict, Any, Optional, Callable
from threading import Thread
import sseclient

from .exceptions import FirebaseException, RealtimeDatabaseException

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
                raise RealtimeDatabaseException("Cannot determine Realtime Database URL")

        self.base_url = db_url.rstrip('/')

    def _build_url(self, path: str, query: Optional[Dict[str, Any]] = None) -> str:
        """Build full URL with path and .json extension."""
        path = path.strip('/')
        url = f"{self.base_url}/{path}.json" if path else f"{self.base_url}/.json"

        params = dict(query) if query else {}
        if self.client.user and self.client.user.get('idToken'):
            params['auth'] = self.client.user['idToken']

        if params:
            url += '?' + urlencode(params)

        return url

    def _request(self, method: str, path: str, allow_404: bool = False, query: Optional[Dict[str, Any]] = None, **kwargs) -> Optional[requests.Response]:
        """
        Internal helper to perform RTDB requests with token refresh support and optional 404 handling.
        """
        headers = kwargs.pop('headers', {}) or {}
        timeout = kwargs.pop('timeout', self.client.timeout)

        # Inject auth header using placeholder so it can be re-rendered after token refresh
        if self.client.user and self.client.user.get('idToken'):
            headers.setdefault('Authorization', 'Bearer {token}')

        def format_headers() -> Dict[str, Any]:
            return self.client._format_headers(headers) if headers else headers

        def perform(url: str) -> requests.Response:
            response = requests.request(method, url, headers=format_headers(), timeout=timeout, **kwargs)
            if allow_404 and response.status_code == 404:
                return response
            response.raise_for_status()
            return response

        url = self._build_url(path, query)

        try:
            response = perform(url)
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401 and self.client.user and self.client.user.get('refreshToken'):
                self.client.auth.refresh_token()
                url = self._build_url(path)  # rebuild with fresh token
                response = perform(url)
            else:
                raise RealtimeDatabaseException(f"Realtime Database error: {exc}") from exc

        return response

    def get(
        self,
        path: str = '',
        default: Any = None,
        order_by: Optional[str] = None,
        equal_to: Optional[Any] = None,
        start_at: Optional[Any] = None,
        end_at: Optional[Any] = None,
        limit_to_first: Optional[int] = None,
        limit_to_last: Optional[int] = None,
        shallow: bool = False
    ) -> Any:
        """
        Read data from Realtime Database.

        :param path: Database path (e.g., 'users/john' or 'messages')
        :param default: Value to return if path doesn't exist
        :param order_by: Field to order by (use '$key' or '$value' for special ordering)
        :param equal_to: Filter equalTo value
        :param start_at: Filter startAt value
        :param end_at: Filter endAt value
        :param limit_to_first: Limit to first N results
        :param limit_to_last: Limit to last N results
        :param shallow: If True, returns shallow keys only
        :return: Data at the specified path
        """
        query: Dict[str, Any] = {}
        if order_by is not None:
            query['orderBy'] = json.dumps(order_by)
        if equal_to is not None:
            query['equalTo'] = json.dumps(equal_to)
        if start_at is not None:
            query['startAt'] = json.dumps(start_at)
        if end_at is not None:
            query['endAt'] = json.dumps(end_at)
        if limit_to_first is not None:
            query['limitToFirst'] = str(limit_to_first)
        if limit_to_last is not None:
            query['limitToLast'] = str(limit_to_last)
        if shallow:
            query['shallow'] = 'true'

        response = self._request(
            'get',
            path,
            headers={'Accept': 'application/json'},
            allow_404=True,
            query=query if query else None
        )

        if response is None or response.status_code == 404:
            return default

        data = response.json()
        if data is None:
            return default
        if self.client.verbose:
            print(f"Data retrieved from {path}")
        return data

    def set(self, path: str, data: Any) -> None:
        """
        Write/replace data at a path (overwrites existing data).

        :param path: Database path
        :param data: Data to write (will be JSON serialized)
        """
        self._request(
            'put',
            path,
            headers={'Content-Type': 'application/json'},
            json=data
        )

        if self.client.verbose:
            print(f"Data set at {path}")

    def push(self, path: str, data: Any) -> str:
        """
        Add data with auto-generated key (like a list append).

        :param path: Database path
        :param data: Data to push
        :return: The auto-generated key
        """
        response = self._request(
            'post',
            path,
            headers={'Content-Type': 'application/json'},
            json=data
        )

        result = response.json() if response is not None else {}
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
        self._request(
            'patch',
            path,
            headers={'Content-Type': 'application/json'},
            json=data
        )

        if self.client.verbose:
            print(f"Data updated at {path}")

    def delete(self, path: str) -> None:
        """
        Delete data at a path.

        :param path: Database path to delete
        """
        self._request('delete', path)

        if self.client.verbose:
            print(f"Data deleted at {path}")

    def stream(
        self,
        path: str,
        callback: Callable[[str, Any], None],
        error_callback: Optional[Callable[[Exception], None]] = None,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0
    ) -> 'StreamListener':
        """
        Stream real-time updates from a path using Server-Sent Events.

        :param path: Database path to stream
        :param callback: Function called on data changes: callback(event_type, data)
                        event_type can be: 'put', 'patch', 'keep-alive', 'cancel', 'auth_revoked'
        :param error_callback: Optional function called on errors
        :param initial_backoff: Initial reconnect delay in seconds
        :param max_backoff: Max reconnect delay in seconds
        :return: StreamListener object to control the stream
        """
        return StreamListener(self, path, callback, error_callback, initial_backoff, max_backoff)


class StreamListener:
    """Handle Server-Sent Events streaming for Realtime Database."""

    def __init__(
        self,
        rtdb: RealtimeDatabase,
        path: str,
        callback: Callable[[str, Any], None],
        error_callback: Optional[Callable[[Exception], None]] = None,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0
    ):
        self.rtdb = rtdb
        self.path = path
        self.callback = callback
        self.error_callback = error_callback
        self.thread: Optional[Thread] = None
        self.running = False
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff

    def _stream_loop(self):
        """Main streaming loop running in thread with auto-reconnect."""
        headers = {
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache'
        }
        backoff = max(self.initial_backoff, 0.1)

        while self.running:
            try:
                response = self.rtdb._request(
                    'get',
                    self.path,
                    headers=headers,
                    stream=True,
                    timeout=None  # keep the stream alive
                )
                if response is None:
                    raise FirebaseException("Stream initialization failed")

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
                        if self.rtdb.client.verbose:
                            print("Keep-alive received")
                    elif event_type in ('cancel', 'auth_revoked'):
                        if self.rtdb.client.verbose:
                            print(f"Stream {event_type}, reconnecting...")
                        break

                # Reset backoff after a successful session
                backoff = 1.0

            except Exception as e:
                if self.error_callback:
                    self.error_callback(e)
                elif self.rtdb.client.verbose:
                    print(f"Stream error: {e}")

            if self.running:
                # Reconnect with backoff
                time.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

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

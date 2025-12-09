"""Main Firebase client module."""

import json
import time
from typing import Dict, Any, Optional, Callable, Literal, Union
import requests

from .auth import Auth
from .firestore import Firestore
from .storage import Storage
from .functions import Functions
from .rtdb import RealtimeDatabase
from .exceptions import FirebaseException


class FirebaseClient:
    """Main client for interacting with Firebase services."""

    def __init__(
        self,
        config: Dict[str, Any],
        verbose: bool = False,
        timeout: Optional[float] = 10,
        retries: int = 2,
        backoff: float = 0.5,
        app_check_token: Optional[Union[str, Callable[[], str]]] = None
    ):
        """
        Initialize Firebase client.

        :param config: Firebase configuration dictionary with keys:
                      - apiKey
                      - projectId
                      - storageBucket
                      - (optional) authDomain, messagingSenderId, appId, databaseURL
        :param verbose: Enable verbose logging
        :param timeout: Default timeout (in seconds) applied to HTTP requests (None for no timeout)
        :param retries: Number of retry attempts for transient errors (429/5xx/connection)
        :param backoff: Initial backoff (seconds) for retries (exponential)
        :param app_check_token: Static token or callable returning token for App Check
        """
        self.config = config
        self.auth = Auth(self)
        self.firestore = Firestore(self)
        self.storage = Storage(self)
        self.functions = Functions(self)
        self.rtdb = RealtimeDatabase(self)
        self.user: Optional[Dict[str, Any]] = None
        self.verbose = verbose
        self.timeout = timeout
        self.retries = max(retries, 0)
        self.backoff = max(backoff, 0.0)
        self.app_check_token = app_check_token

    def _request(
        self,
        type: Literal['post', 'get', 'delete', 'patch'],
        **kwargs
    ) -> requests.Response:
        """Make an HTTP request with formatted headers."""
        if kwargs.get('headers'):
            kwargs['headers'] = self._format_headers(kwargs['headers'])

        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout

        if type == 'post':
            response = requests.post(**kwargs)
        elif type == 'get':
            response = requests.get(**kwargs)
        elif type == 'delete':
            response = requests.delete(**kwargs)
        elif type == 'patch':
            response = requests.patch(**kwargs)
        else:
            raise ValueError(f"Unsupported request type: {type}")

        return response

    def _make_request(
        self,
        type: Literal['post', 'get', 'delete', 'patch'],
        default: Optional[Callable[[], Any]] = None,
        **kwargs
    ) -> Any:
        """
        Make an HTTP request with automatic token refresh and error handling.

        :param type: HTTP method type
        :param default: Optional callback to return default value on NOT_FOUND
        :param kwargs: Arguments to pass to requests
        :return: Response object or default value
        """
        request_kwargs = dict(kwargs)
        original_headers = request_kwargs.pop('headers', None)

        def formatted_kwargs() -> Dict[str, Any]:
            updated = dict(request_kwargs)
            if original_headers:
                updated['headers'] = self._format_headers(original_headers)
            return updated

        attempt = 0
        response: Optional[requests.Response] = None
        while True:
            try:
                response = self._request(type, **formatted_kwargs())
            except requests.exceptions.RequestException as exc:
                if attempt < self.retries:
                    delay = self.backoff * (2 ** attempt)
                    if self.verbose:
                        print(f"Transient error {exc}, retrying in {delay:.2f}s...")
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise

            # Retry on 429/5xx
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                delay = self.backoff * (2 ** attempt)
                if self.verbose:
                    print(f"Retrying request after HTTP {response.status_code} in {delay:.2f}s...")
                time.sleep(delay)
                attempt += 1
                continue
            break

        if response.status_code >= 400:
            try:
                error = response.json().get('error', {})
            except (ValueError, KeyError):
                error = {}

            # Try refreshing token if unauthenticated
            if self.user is not None and self.user.get("idToken") and error.get('status') == 'UNAUTHENTICATED':
                self.auth.refresh_token()
                if original_headers:
                    request_kwargs['headers'] = self._format_headers(original_headers)
                response = self._request(type, **request_kwargs)

                if response.status_code >= 400:
                    try:
                        error = response.json().get('error', {})
                    except (ValueError, KeyError):
                        error = {}

                    if error.get('status') == 'NOT_FOUND':
                        if default:
                            return default()
                        else:
                            raise FirebaseException("NOT_FOUND")
                    else:
                        msg = error.get('status') or error.get('message') or "Unknown Firebase error"
                        raise FirebaseException(msg)

            elif error.get('status') == 'NOT_FOUND':
                if default:
                    return default()
                else:
                    raise FirebaseException('NOT_FOUND')
            else:
                msg = error.get('status') or error.get('message') or "Unknown Firebase error"
                raise FirebaseException(msg)

        return response

    def _format_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Format headers by replacing token placeholder with actual token."""
        formatted = headers.copy()
        if formatted.get('Authorization') and self.user:
            formatted['Authorization'] = formatted['Authorization'].format(token=self.user['idToken'])
        # Auto-inject App Check token if provided
        if 'X-Firebase-AppCheck' not in formatted:
            app_check = self._get_app_check_token()
            if app_check:
                formatted['X-Firebase-AppCheck'] = app_check
        return formatted

    def _get_app_check_token(self) -> Optional[str]:
        """Retrieve App Check token (static or callable)."""
        if callable(self.app_check_token):
            try:
                return self.app_check_token()
            except Exception:
                return None
        return self.app_check_token

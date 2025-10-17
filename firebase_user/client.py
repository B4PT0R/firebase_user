"""Main Firebase client module."""

import json
from typing import Dict, Any, Optional, Callable, Literal
import requests

from .auth import Auth
from .firestore import Firestore
from .storage import Storage
from .functions import Functions
from .rtdb import RealtimeDatabase
from .exceptions import FirebaseException


class FirebaseClient:
    """Main client for interacting with Firebase services."""

    def __init__(self, config: Dict[str, Any], verbose: bool = False):
        """
        Initialize Firebase client.

        :param config: Firebase configuration dictionary with keys:
                      - apiKey
                      - projectId
                      - storageBucket
                      - (optional) authDomain, messagingSenderId, appId, databaseURL
        :param verbose: Enable verbose logging
        """
        self.config = config
        self.auth = Auth(self)
        self.firestore = Firestore(self)
        self.storage = Storage(self)
        self.functions = Functions(self)
        self.rtdb = RealtimeDatabase(self)
        self.user: Optional[Dict[str, Any]] = None
        self.verbose = verbose

    def _request(
        self,
        type: Literal['post', 'get', 'delete', 'patch'],
        **kwargs
    ) -> requests.Response:
        """Make an HTTP request with formatted headers."""
        if kwargs.get('headers'):
            kwargs['headers'] = self._format_headers(kwargs['headers'])

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
        response = self._request(type, **kwargs)

        if response.status_code >= 400:
            try:
                error = response.json().get('error', {})
            except (ValueError, KeyError):
                error = {}

            # Try refreshing token if unauthenticated
            if self.user is not None and self.user.get("idToken") and error.get('status') == 'UNAUTHENTICATED':
                self.auth.refresh_token()
                response = self._request(type, **kwargs)

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
        return formatted

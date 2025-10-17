"""Cloud Functions module for Firebase client."""

import json
from typing import TYPE_CHECKING, Dict, Any, Optional

from .exceptions import FirebaseException

if TYPE_CHECKING:
    from .client import FirebaseClient


class Functions:
    """Handle Firebase Cloud Functions (callable) operations."""

    def __init__(self, client: 'FirebaseClient'):
        self.client = client
        # Default region, can be overridden
        self.region = 'us-central1'

    def call(
        self,
        function_name: str,
        data: Optional[Any] = None,
        region: Optional[str] = None
    ) -> Any:
        """
        Call a Firebase Cloud Function (https.onCall).

        :param function_name: Name of the callable function
        :param data: Data to pass to the function (will be JSON serialized)
        :param region: Region where function is deployed (default: us-central1)
        :return: The data returned by the function
        """
        region = region or self.region
        project_id = self.client.config.get('projectId')

        if not project_id:
            raise ValueError("projectId not found in Firebase config")

        # Callable functions endpoint format
        url = f"https://{region}-{project_id}.cloudfunctions.net/{function_name}"

        headers = {
            'Content-Type': 'application/json; charset=utf-8'
        }

        # Add auth token if user is authenticated
        if self.client.user and self.client.user.get('idToken'):
            headers['Authorization'] = f"Bearer {self.client.user['idToken']}"

        # Wrap data in required format for callable functions
        body = {'data': data if data is not None else {}}

        response = self.client._make_request(
            type='post',
            url=url,
            headers=headers,
            json=body
        )

        result = response.json()

        # Check for function error
        if 'error' in result:
            error = result['error']
            error_msg = error.get('message', 'Unknown function error')
            raise FirebaseException(f"Function error: {error_msg}")

        # Return the result data
        return result.get('result')

    def set_region(self, region: str) -> None:
        """
        Set the default region for Cloud Functions.

        :param region: Region name (e.g., 'us-central1', 'europe-west1')
        """
        self.region = region
        if self.client.verbose:
            print(f"Cloud Functions region set to: {region}")

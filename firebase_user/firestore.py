"""Firestore module for Firebase client."""

import time
from threading import Thread
from queue import Queue
from typing import TYPE_CHECKING, Dict, Any, Optional, Callable, List, Tuple, Literal

from .utils import to_typed_dict, to_dict, convert_in
from .exceptions import FirebaseException

if TYPE_CHECKING:
    from .client import FirebaseClient


class Listener:
    """Listen for changes to a Firestore document."""

    def __init__(
        self,
        client: 'FirebaseClient',
        collection: str,
        document: str,
        interval: int = 3,
        timeout: Optional[int] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.client = client
        self.interval = interval
        self.timeout = timeout
        self.callback = callback
        self.collection = collection
        self.document = document
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{self.client.config['projectId']}/databases/(default)/documents"
        self.stop_listening = False
        self.listener: Optional[Thread] = None
        self.queue: Optional[Queue] = None

    def listen(self) -> None:
        """
        Start a listening loop to wait for a change in a given firestore document.
        Will make a read request every <interval> seconds until a change is detected or <timeout> is reached.
        """
        self.stop_listening = False
        last_data = self.client.firestore.get_document(self.collection, self.document)
        if self.client.verbose:
            print("Now listening for changes in the document...")
        timeout = self.timeout or 3600
        timer = 0
        while timer < timeout and not self.stop_listening:
            time.sleep(self.interval)
            timer += self.interval
            current_data = self.client.firestore.get_document(self.collection, self.document)
            if current_data != last_data:
                if self.client.verbose:
                    print("Change detected.")
                if self.callback:
                    self.callback(current_data)
                if self.queue:
                    self.queue.put(current_data)
                last_data = current_data
        if self.queue:
            self.queue.put("<STOPPED>")
        self.stop_listening = False
        if self.client.verbose:
            print("Finished listening.")

    def start(self) -> None:
        """Start listening in a background thread."""
        self.queue = Queue()
        self.listener = Thread(target=self.listen)
        self.listener.start()

    def stop(self) -> None:
        """Stop listening and wait for the thread to finish."""
        self.stop_listening = True
        if self.listener is not None:
            self.listener.join()
            self.listener = None

    def get_data(self) -> Any:
        """Get the next data item from the queue (blocking)."""
        if self.queue is None:
            raise RuntimeError("Listener not started.")
        return self.queue.get()

    @property
    def is_listening(self) -> bool:
        """Check if the listener is currently active."""
        return self.listener is not None and not self.stop_listening


class Firestore:
    """Handle Firestore operations."""

    def __init__(self, client: 'FirebaseClient'):
        self.client = client
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{self.client.config['projectId']}/databases/(default)/documents"

    def get_user_data(self) -> Optional[Dict[str, Any]]:
        """Get the current user's document from the 'users' collection."""
        if not self.client.user or not self.client.user.get('email'):
            raise ValueError("No authenticated user.")
        return self.get_document('users', self.client.user['email'])

    def document_exists(self, collection: str, document: str) -> bool:
        """
        Check if a document exists in Firestore.

        :param collection: Collection path
        :param document: Document ID
        :return: True if document exists, False otherwise
        """
        return self.get_document(collection, document) is not None

    def get_document(self, collection: str, document: str, default: Any = None) -> Optional[Dict[str, Any]]:
        """
        Get a document from Firestore.
        Supports subcollections using path notation (e.g., 'users/john/posts', 'post1').

        :param collection: Collection path
        :param document: Document ID
        :param default: Value to return if document doesn't exist (default: None)
        :return: Document data as dict, or default value if not found
        """
        url = f"{self.base_url}/{collection}/{document}"
        headers = {'Authorization': "Bearer {token}"}

        try:
            response = self.client._make_request(type='get', url=url, headers=headers)
            output = to_dict(response.json())
            if self.client.verbose:
                print("Document successfully fetched from firestore.")
            return output
        except FirebaseException as e:
            if "NOT_FOUND" in str(e):
                if self.client.verbose:
                    print(f"Document not found: {collection}/{document}")
                return default
            raise

    def set_user_data(self, data: Dict[str, Any]) -> None:
        """Set the current user's document in the 'users' collection."""
        if not self.client.user or not self.client.user.get('email'):
            raise ValueError("No authenticated user.")
        self.set_document('users', self.client.user['email'], data)

    def set_document(self, collection: str, document: str, data: Dict[str, Any]) -> None:
        """
        Set a document in Firestore (creates or updates entire document).
        Supports subcollections using path notation (e.g., 'users/john/posts', 'post1').
        """
        url = f"{self.base_url}/{collection}/{document}"
        headers = {'Authorization': "Bearer {token}", 'Content-Type': 'application/json'}
        formatted_data = to_typed_dict(data)
        self.client._make_request(type='patch', url=url, headers=headers, json=formatted_data)
        if self.client.verbose:
            print("Document successfully set in firestore.")

    def delete_document(self, collection: str, document: str) -> None:
        """
        Delete a document from Firestore.
        Supports subcollections using path notation (e.g., 'users/john/posts', 'post1').
        """
        url = f"{self.base_url}/{collection}/{document}"
        headers = {'Authorization': "Bearer {token}"}
        self.client._make_request(type='delete', url=url, headers=headers)
        if self.client.verbose:
            print("Document successfully deleted.")

    def update_document(self, collection: str, document: str, data: Dict[str, Any]) -> None:
        """
        Update specific fields in a document without overwriting the entire document.
        Only the fields specified in data will be updated.
        Supports subcollections using path notation (e.g., 'users/john/posts', 'post1').
        """
        url = f"{self.base_url}/{collection}/{document}"
        headers = {'Authorization': "Bearer {token}", 'Content-Type': 'application/json'}

        # Build updateMask for partial update
        field_paths = list(data.keys())
        update_mask = '&'.join([f'updateMask.fieldPaths={field}' for field in field_paths])
        url_with_mask = f"{url}?{update_mask}"

        formatted_data = to_typed_dict(data)
        self.client._make_request(type='patch', url=url_with_mask, headers=headers, json=formatted_data)
        if self.client.verbose:
            print(f"Document successfully updated: {', '.join(field_paths)}")

    def list_documents(self, collection_path: str, page_size: int = 100) -> List[Dict[str, Any]]:
        """
        List all documents in a collection (supports subcollections).

        :param collection_path: Collection path (e.g., 'users' or 'users/john/posts')
        :param page_size: Number of documents per page (max 300)
        :return: List of documents with their data
        """
        url = f"{self.base_url}/{collection_path}"
        headers = {'Authorization': "Bearer {token}"}
        params = {'pageSize': min(page_size, 300)}

        all_documents = []
        page_token = None

        while True:
            if page_token:
                params['pageToken'] = page_token

            response = self.client._make_request(
                type='get',
                url=url,
                headers=headers,
                params=params,
                default=lambda: {"documents": []}
            )

            result = response.json() if hasattr(response, 'json') else response
            documents = result.get('documents', [])

            for doc in documents:
                doc_data = to_dict(doc)
                # Extract document ID from name
                doc_id = doc['name'].split('/')[-1]
                all_documents.append({'id': doc_id, **doc_data})

            page_token = result.get('nextPageToken')
            if not page_token:
                break

        if self.client.verbose:
            print(f"Listed {len(all_documents)} documents from {collection_path}")

        return all_documents

    def query(
        self,
        collection_path: str,
        where: Optional[List[Tuple[str, str, Any]]] = None,
        order_by: Optional[List[Tuple[str, str]]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query documents in a collection with filters and ordering.

        :param collection_path: Collection path (e.g., 'users' or 'users/john/posts')
        :param where: List of (field, operator, value) tuples.
                     Operators: '==', '<', '<=', '>', '>=', '!=', 'in', 'array-contains'
        :param order_by: List of (field, direction) tuples. Direction: 'ASCENDING' or 'DESCENDING'
        :param limit: Maximum number of results
        :return: List of documents matching the query
        """
        # Build structured query
        structured_query: Dict[str, Any] = {
            'from': [{'collectionId': collection_path.split('/')[-1]}]
        }

        # Add where filters
        if where:
            filters = []
            for field, op, value in where:
                op_map = {
                    '==': 'EQUAL',
                    '<': 'LESS_THAN',
                    '<=': 'LESS_THAN_OR_EQUAL',
                    '>': 'GREATER_THAN',
                    '>=': 'GREATER_THAN_OR_EQUAL',
                    '!=': 'NOT_EQUAL',
                    'in': 'IN',
                    'array-contains': 'ARRAY_CONTAINS'
                }

                filter_obj = {
                    'fieldFilter': {
                        'field': {'fieldPath': field},
                        'op': op_map.get(op, 'EQUAL'),
                        'value': convert_in(value)
                    }
                }
                filters.append(filter_obj)

            if len(filters) == 1:
                structured_query['where'] = filters[0]
            else:
                # Multiple filters: use composite filter with AND
                structured_query['where'] = {
                    'compositeFilter': {
                        'op': 'AND',
                        'filters': filters
                    }
                }

        # Add orderBy
        if order_by:
            structured_query['orderBy'] = [
                {
                    'field': {'fieldPath': field},
                    'direction': direction.upper()
                }
                for field, direction in order_by
            ]

        # Add limit
        if limit:
            structured_query['limit'] = limit

        # Determine parent path for subcollections
        parent_parts = collection_path.split('/')[:-1]
        if parent_parts:
            parent = f"{self.base_url}/{'/'.join(parent_parts)}"
        else:
            parent = self.base_url

        url = f"{parent}:runQuery"
        headers = {'Authorization': "Bearer {token}", 'Content-Type': 'application/json'}

        response = self.client._make_request(
            type='post',
            url=url,
            headers=headers,
            json={'structuredQuery': structured_query}
        )

        results = []
        response_data = response.json()

        # runQuery returns array of results
        if isinstance(response_data, list):
            for item in response_data:
                if 'document' in item:
                    doc = item['document']
                    doc_data = to_dict(doc)
                    doc_id = doc['name'].split('/')[-1]
                    results.append({'id': doc_id, **doc_data})

        if self.client.verbose:
            print(f"Query returned {len(results)} documents from {collection_path}")

        return results

    def listener(
        self,
        collection: str,
        document: str,
        interval: int = 3,
        timeout: Optional[int] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Listener:
        """Create a document listener."""
        return Listener(self.client, collection, document, interval=interval, timeout=timeout, callback=callback)

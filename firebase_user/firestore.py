"""Firestore module for Firebase client."""

import time
from threading import Thread
from queue import Queue
from typing import TYPE_CHECKING, Dict, Any, Optional, Callable, List, Tuple, Literal

from .utils import to_typed_dict, to_dict, convert_in
from .exceptions import FirebaseException, FirestoreException

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
            raise FirestoreException("No authenticated user.")
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
            raise FirestoreException(str(e)) from e

    def set_user_data(self, data: Dict[str, Any]) -> None:
        """Set the current user's document in the 'users' collection."""
        if not self.client.user or not self.client.user.get('email'):
            raise FirestoreException("No authenticated user.")
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
        limit: Optional[int] = None,
        start_at: Optional[Any] = None,
        end_at: Optional[Any] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query documents in a collection with filters and ordering.

        :param collection_path: Collection path (e.g., 'users' or 'users/john/posts')
        :param where: List of (field, operator, value) tuples.
                     Operators: '==', '<', '<=', '>', '>=', '!=', 'in', 'array-contains'
        :param order_by: List of (field, direction) tuples. Direction: 'ASCENDING' or 'DESCENDING'
        :param limit: Maximum number of results
        :param start_at: Cursor start value(s) (single value or list matching order_by)
        :param end_at: Cursor end value(s) (single value or list matching order_by)
        :param offset: Number of results to skip (offset)
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
                    'not-in': 'NOT_IN',
                    'array-contains': 'ARRAY_CONTAINS',
                    'array-contains-any': 'ARRAY_CONTAINS_ANY'
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
        if offset:
            structured_query['offset'] = offset

        def _cursor_payload(value: Any) -> Dict[str, Any]:
            values = value if isinstance(value, (list, tuple)) else [value]
            return {'values': [convert_in(v) for v in values], 'before': False}

        if start_at is not None:
            structured_query['startAt'] = _cursor_payload(start_at)
        if end_at is not None:
            structured_query['endAt'] = _cursor_payload(end_at)

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

    # -------- Batch / commit helpers --------
    def build_set_write(
        self,
        collection: str,
        document: str,
        data: Dict[str, Any],
        merge_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Build a Firestore write payload for set/update operations.
        """
        doc_name = f"{self.base_url}/{collection}/{document}"
        write: Dict[str, Any] = {
            "update": {
                "name": doc_name,
                **to_typed_dict(data)
            }
        }
        if merge_fields:
            write["updateMask"] = {"fieldPaths": merge_fields}
        return write

    def build_delete_write(self, collection: str, document: str) -> Dict[str, Any]:
        """Build a Firestore write payload for deletions."""
        doc_name = f"{self.base_url}/{collection}/{document}"
        return {"delete": doc_name}

    def commit(self, writes: List[Dict[str, Any]], transaction: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Perform a commit request with a list of write operations.
        Use build_set_write / build_delete_write to help build the payload.
        You can pass a transaction ID from begin_transaction.
        """
        if not writes:
            return []

        url = f"{self.base_url}:commit"
        headers = {'Authorization': "Bearer {token}", 'Content-Type': 'application/json'}
        body: Dict[str, Any] = {"writes": writes}
        if transaction:
            body["transaction"] = transaction
        response = self.client._make_request(
            type='post',
            url=url,
            headers=headers,
            json=body
        )
        result = response.json()
        return result.get("writeResults", [])

    def build_transform_write(
        self,
        collection: str,
        document: str,
        transforms: List[Tuple[str, str, Any]]
    ) -> Dict[str, Any]:
        """
        Build a transform write (increment, arrayUnion, arrayRemove).
        """
        field_transforms = []
        for field, op, value in transforms:
            if op == 'increment':
                field_transforms.append({
                    "fieldPath": field,
                    "increment": convert_in(value)
                })
            elif op == 'arrayUnion':
                values = value if isinstance(value, (list, tuple)) else [value]
                field_transforms.append({
                    "fieldPath": field,
                    "appendMissingElements": {"values": [convert_in(v) for v in values]}
                })
            elif op == 'arrayRemove':
                values = value if isinstance(value, (list, tuple)) else [value]
                field_transforms.append({
                    "fieldPath": field,
                    "removeAllFromArray": {"values": [convert_in(v) for v in values]}
                })
            else:
                raise FirestoreException(f"Unsupported transform operation: {op}")

        doc_name = f"{self.base_url}/{collection}/{document}"
        return {
            "transform": {
                "document": doc_name,
                "fieldTransforms": field_transforms
            }
        }

    def begin_transaction(self, read_only: bool = False) -> str:
        """Begin a Firestore transaction and return its ID."""
        url = f"{self.base_url}:beginTransaction"
        headers = {'Authorization': "Bearer {token}", 'Content-Type': 'application/json'}
        options = {"readOnly": {}} if read_only else {}
        response = self.client._make_request(
            type='post',
            url=url,
            headers=headers,
            json={"options": options} if options else {}
        )
        transaction = response.json().get("transaction")
        if not transaction:
            raise FirestoreException("Failed to start transaction")
        return transaction

    def rollback(self, transaction: str) -> None:
        """Rollback a transaction."""
        url = f"{self.base_url}:rollback"
        headers = {'Authorization': "Bearer {token}", 'Content-Type': 'application/json'}
        self.client._make_request(
            type='post',
            url=url,
            headers=headers,
            json={"transaction": transaction}
        )

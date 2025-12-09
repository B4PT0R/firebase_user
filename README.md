# firebase_user

A client-side Firebase REST API interface designed for Streamlit applications - no admin credentials required.

This package provides a convenient client interface for the Firebase REST API without using the firebase-admin SDK. It only requires your Firebase app config (which can be safely exposed in client code), making it perfect for Streamlit apps and other client-side applications.

**Key Features:**
- Authentication - Email/password auth, session persistence, password reset emails
- Firestore - CRUD operations, queries, subcollections support
- Storage - File upload/download with folder sync
- Cloud Functions - Call serverless functions (callable)
- Realtime Database - Real-time data sync with SSE streaming
- Streamlit-ready - Built-in helpers for session management
- Type hints - Full type annotations for better DX
- App Check ready - Optional App Check token injection
- Secure - No admin credentials needed, relies on Firebase Security Rules

## Installation

```bash
pip install firebase-user
```

## Quick Start

### Setup

```python
from firebase_user import FirebaseClient

# Get your Firebase app config from Firebase Console
config = {
    "apiKey": "...",
    "authDomain": "...",
    "projectId": "...",
    "storageBucket": "...",
    "messagingSenderId": "...",
    "appId": "..."
}

client = FirebaseClient(config)
# Optional: tweak HTTP behavior
# client = FirebaseClient(config, timeout=10, retries=2, backoff=0.5, app_check_token="APP_CHECK_TOKEN")
``` 

### Authentication

```python
# Sign up new user
client.auth.sign_up("user@example.com", "password123")

# Sign in
client.auth.sign_in("user@example.com", "password123")

# Sign in with OAuth provider (e.g., Google)
# client.auth.sign_in_with_oauth("google.com", id_token="GOOGLE_ID_TOKEN")
# Supported providerIds include: google.com, github.com, apple.com, facebook.com, twitter.com, microsoft.com, yahoo.com

# Check authentication
print(client.auth.authenticated)  # True

# Get user info (safe for display - no tokens)
user_info = client.auth.get_user_info()
# -> {'uid': '...', 'email': '...', 'emailVerified': False, ...}

# Session persistence (for Streamlit)
session_data = client.auth.to_session_dict()  # Save to st.session_state
client.auth.from_session_dict(session_data)   # Restore on page reload

# Or directly with refresh token
refresh_token = client.auth.get_refresh_token()
client.auth.restore_session(refresh_token)

# Password reset (sends email via Firebase - free!)
client.auth.send_password_reset_email("user@example.com")

# Email verification
client.auth.send_email_verification()

# Update profile
client.auth.update_profile(display_name="John Doe")
client.auth.update_email("new@mail.com")

# Link/Unlink OAuth providers
# client.auth.link_provider("google.com", id_token="GOOGLE_ID_TOKEN")
# client.auth.unlink_provider("google.com")

# Change password
client.auth.change_password("new_password")

# Log out
client.auth.log_out()
```

Tips:
- `request_uri` can be any valid URL; it just needs to match the authorized domains on your Firebase project.
- For Apple/Facebook/Twitter etc., provide the provider access token instead of an ID token.
- Use `to_session_dict()` / `from_session_dict()` or `restore_session(refresh_token)` to keep users signed in across page reloads.

### Firestore

```python
# Get/Set user's document
data = client.firestore.get_user_data()
client.firestore.set_user_data({'age': 30, 'city': 'Paris'})

# Get document (returns None if not found)
doc = client.firestore.get_document('users', 'john')
# With default value
doc = client.firestore.get_document('users', 'john', default={})

# Check if document exists
if client.firestore.document_exists('users', 'john'):
    print("User exists!")

# Set/Update document
client.firestore.set_document('posts', 'post1', {'title': 'Hello', 'views': 0})

# Partial update (only specified fields)
client.firestore.update_document('posts', 'post1', {'views': 100})

# Query with cursors/offset
posts = client.firestore.query(
    'posts',
    where=[('published', '==', True)],
    order_by=[('created_at', 'DESCENDING')],
    limit=10,
    start_at='2024-01-01T00:00:00Z',
    offset=5
)

# Delete document
client.firestore.delete_document('posts', 'post1')

# List all documents in collection
users = client.firestore.list_documents('users')
# -> [{'id': 'john', 'age': 30, ...}, {'id': 'jane', ...}]

# Query with filters
posts = client.firestore.query(
    'posts',
    where=[
        ('published', '==', True),
        ('views', '>', 100)
    ],
    order_by=[('created_at', 'DESCENDING')],
    limit=10
)

# Subcollections support
user_posts = client.firestore.list_documents('users/john/posts')
post = client.firestore.get_document('users/john/posts', 'post1')

# Document listener (polling-based)
def on_change(data):
    print(f"Document changed: {data}")

listener = client.firestore.listener('users', 'john', callback=on_change)
listener.start()
# ... later
listener.stop()

# Batch writes (commit)
writes = [
    client.firestore.build_set_write('posts', 'post1', {'title': 'Hello', 'views': 0}),
    client.firestore.build_delete_write('posts', 'old_post')
]
results = client.firestore.commit(writes)

# Field transforms (increment/arrayUnion/arrayRemove)
transform = client.firestore.build_transform_write(
    'posts',
    'post1',
    [
        ('views', 'increment', 1),
        ('tags', 'arrayUnion', ['news'])
    ]
)
client.firestore.commit([transform])

# Transactions
tx = client.firestore.begin_transaction()
# ... perform reads with the transaction via HTTP (advanced) ...
client.firestore.commit([transform], transaction=tx)
client.firestore.rollback(tx)  # or rollback if needed
``` 

### Storage

```python
# List files in user's storage
files = client.storage.list_files()

# Upload/Download files
client.storage.upload_file('local.txt', 'remote/path.txt')
client.storage.download_file('remote/path.txt', 'local.txt')
# Large files with resumable upload (safer on flaky networks)
client.storage.upload_file_resumable('big.bin', 'remote/big.bin')
client.storage.upload_file('local.txt', 'remote/path.txt', content_type='text/plain')  # override content type
# Chunked resumable upload with metadata
client.storage.upload_file_resumable('big.bin', 'remote/big.bin', chunk_size=256*1024, metadata={'role': 'backup'})
# Fetch metadata / download URL
meta = client.storage.get_metadata('remote/path.txt')
download_url = client.storage.get_download_url('remote/path.txt')

# Delete file
client.storage.delete_file('remote/path.txt')

# Unidirectional sync: local -> cloud (deletes remote files not in local)
client.storage.dump_folder('./my_folder')

# Unidirectional sync: cloud -> local (deletes local files not in remote)
client.storage.load_folder('./my_folder')

# Bidirectional sync: merge local and remote (no deletions, newer wins)
client.storage.sync_folder('./my_folder')  # Best for most use cases!
```

### Cloud Functions (Callable)

```python
# Call a Cloud Function (https.onCall)
result = client.functions.call('processPayment', {
    'amount': 100,
    'currency': 'EUR',
    'userId': 'john'
})

# Specify region if not us-central1
result = client.functions.call('myFunction', data={'key': 'value'}, region='europe-west1')

# Set default region
client.functions.set_region('europe-west1')
```

Notes:
- App Check token (if provided to `FirebaseClient`) is sent automatically in `X-Firebase-AppCheck`.
- Functions calls include `Authorization: Bearer <idToken>` when the user is logged in.

### Realtime Database

```python
# Read data
messages = client.rtdb.get('messages')
user_data = client.rtdb.get('users/john', default={})

# Write data (replaces existing)
client.rtdb.set('users/john', {'name': 'John', 'age': 30})

# Push data with auto-generated key
key = client.rtdb.push('messages', {
    'text': 'Hello!',
    'timestamp': '2024-01-01'
})
# -> Returns: '-N7qPZ9xK...' (auto-generated key)

# Update specific fields
client.rtdb.update('users/john', {'age': 31, 'city': 'Paris'})

# Query filters
messages_page = client.rtdb.get('messages', order_by='$key', start_at='-N7', limit_to_first=20)

# Delete data
client.rtdb.delete('messages/old_message')

# Real-time streaming (Server-Sent Events)
def on_data_change(event_type, data):
    print(f"{event_type}: {data}")

stream = client.rtdb.stream('messages', callback=on_data_change)
stream.start()
# ... later
stream.stop()
```

## Streamlit Integration Example

```python
import streamlit as st
from firebase_user import FirebaseClient

# Initialize client
if 'client' not in st.session_state:
    st.session_state.client = FirebaseClient(config)

client = st.session_state.client

# Restore session on page reload
if 'refresh_token' in st.session_state and not client.auth.authenticated:
    try:
        client.auth.restore_session(st.session_state.refresh_token)
    except:
        pass  # Token expired

# Login UI
if not client.auth.authenticated:
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            client.auth.sign_in(email, password)
            st.session_state.update(client.auth.to_session_dict())
            st.rerun()

    with col2:
        if st.button("Sign Up"):
            client.auth.sign_up(email, password)
            st.session_state.update(client.auth.to_session_dict())
            st.rerun()
else:
    # User authenticated
    user_info = client.auth.get_user_info()
    st.write(f"Welcome {user_info['email']}!")

    if st.button("Logout"):
        client.auth.log_out()
        del st.session_state['refresh_token']
        st.rerun()
```

## Security Notes

**Important:** This package uses Firebase Authentication client-side tokens, not admin credentials. Your Firebase Security Rules are the **only** line of defense for data access control.

If you use App Check, pass a token (string or callable) with `app_check_token` when constructing `FirebaseClient`; it will be sent in `X-Firebase-AppCheck` automatically.

Example Firestore Security Rules:
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Users can only read/write their own document
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.token.email == userId;
    }

    // Users can read public posts, but only edit their own
    match /posts/{postId} {
      allow read: if resource.data.published == true;
      allow write: if request.auth != null && request.auth.uid == resource.data.authorId;
    }
  }
}
```

## API Reference

### FirebaseClient

- `auth` - Authentication methods
- `firestore` - Firestore operations
- `storage` - Cloud Storage operations
- `functions` - Cloud Functions (callable)
- `rtdb` - Realtime Database operations
- Exceptions: `AuthException`, `FirestoreException`, `StorageException`, `FunctionsException`, `RealtimeDatabaseException` (all subclass `FirebaseException`)

### Auth Methods

- `sign_in(email, password)` - Authenticate user
- `sign_up(email, password)` - Create new user
- `sign_in_with_oauth(provider_id, access_token=None, id_token=None, request_uri="http://localhost")` - Sign in with OAuth provider (Google/Apple/GitHub/etc.)
- `sign_in_with_user_object(user)` - Restore from user object
- `restore_session(refresh_token)` - Restore from refresh token
- `get_user_info()` - Get public user data (no tokens)
- `get_refresh_token()` - Get refresh token
- `to_session_dict()` / `from_session_dict()` - Session serialization
- `send_password_reset_email(email)` - Send reset email (Firebase emails, free!)
- `send_email_verification()` - Send verification email
- `update_profile(display_name, photo_url)` - Update profile
- `update_email(new_email)` - Update email
- `change_password(new_password)` - Change password
- `link_provider(provider_id, access_token=None, id_token=None, request_uri="http://localhost")` - Link OAuth provider to user
- `unlink_provider(provider_ids)` - Unlink provider(s) from user
- `delete_user()` - Delete current user
- `log_out()` - Log out
- `is_valid(token)` - Check if token is valid
- `authenticated` - Property: is user authenticated

### Firestore Methods

- `get_document(collection, document, default=None)` - Get document (returns None if not found)
- `document_exists(collection, document)` - Check if document exists
- `set_document(collection, document, data)` - Set entire document
- `update_document(collection, document, data)` - Update specific fields
- `delete_document(collection, document)` - Delete document
- `list_documents(collection_path, page_size=100)` - List all documents
- `query(collection_path, where=None, order_by=None, limit=None)` - Query documents
- `get_user_data()` / `set_user_data(data)` - User document shortcuts
- `listener(collection, document, ...)` - Create document listener
- `build_set_write(collection, document, data, merge_fields=None)` - Helper for commit payloads
- `build_delete_write(collection, document)` - Helper for commit payloads
- `commit(writes)` - Send batch commit request

### Storage Methods

- `list_files()` - List files with metadata
- `upload_file(local_path, remote_path)` - Upload file
- `upload_file_resumable(local_path, remote_path, content_type=None, metadata=None)` - Resumable upload
- `download_file(remote_path, local_path)` - Download file
- `delete_file(remote_path)` - Delete file
- `dump_folder(local_folder)` - Sync local -> cloud
- `load_folder(local_folder)` - Sync cloud -> local
- `sync_folder(local_folder)` - Bidirectional sync

### Cloud Functions Methods

- `call(function_name, data=None, region=None)` - Call a callable Cloud Function
- `set_region(region)` - Set default region for functions

### Realtime Database Methods

- `get(path, default=None)` - Read data from path
- `set(path, data)` - Write/replace data at path
- `push(path, data)` - Add data with auto-generated key (returns key)
- `update(path, data)` - Update specific fields
- `delete(path)` - Delete data at path
- `stream(path, callback, error_callback=None)` - Real-time streaming (SSE)

## Requirements

- Python >= 3.7
- requests >= 2.25.0
- sseclient-py >= 1.7.0 (for Realtime Database streaming)

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please open an issue or PR on [GitHub](https://github.com/B4PT0R/firebase_user).

## Contact

Baptiste Ferrand - bferrand.maths@gmail.com

# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2025-10-17

### Added

#### CLI Tool - `firebase-user-init`
- **Interactive project wizard** for scaffolding Firebase + Streamlit apps
- **4 preset templates:**
  - `simple` - Basic auth + Firestore
  - `dashboard` - Analytics dashboard with charts
  - `collaborative` - Real-time collaboration with RTDB
  - `saas` - Full-stack SaaS starter
- **Auto-generated project structure:**
  - Streamlit app (3 template styles: basic, advanced, dashboard)
  - Firebase configuration
  - Requirements.txt with dependencies
  - .env file with credentials
  - .gitignore
  - README with setup instructions
- **Firebase Admin SDK integration** (optional) for advanced setup
- Command-line options for non-interactive usage

#### Storage Module
- `sync_folder()` - Bidirectional folder sync (merges local ↔ remote)
  - No deletions, only adds and updates
  - Uses MD5 hash to detect changes
  - Uses timestamps to resolve conflicts (newer wins)

### Changed
- **Utils:** Fixed deprecation warning for `datetime.utcfromtimestamp()`
  - Now uses `datetime.fromtimestamp(tz=timezone.utc)` (timezone-aware)

### Documentation
- Added CLI usage section to README
- Created CLI_USAGE.md with detailed examples
- Updated all examples to include new features

## [0.2.0] - Previous Release

### Added

#### Authentication
- `restore_session(refresh_token)` - Restore user session from refresh token
- `get_user_info()` - Get public user info (no tokens)
- `send_password_reset_email(email)` - Send password reset email (Firebase's free service)
- `send_email_verification()` - Send email verification
- `update_profile(display_name, photo_url)` - Update user profile
- `to_session_dict()` / `from_session_dict()` - Session persistence helpers

#### Firestore
- `list_documents(collection_path, page_size=100)` - List all documents with pagination
- `query(collection_path, where, order_by, limit)` - Advanced queries with filters
- `update_document(collection, document, data)` - Partial document updates
- `document_exists(collection, document)` - Check document existence
- `get_document()` now returns `None` if not found (+ optional `default` parameter)
- Subcollections support across all methods

#### Storage
- Migrated to `pathlib` for cross-platform path handling
- Added MD5 hash to file metadata
- `has_changed(file1, file2)` - Compare files by MD5 hash
- `is_newer(file1, file2)` - Compare files by timestamp
- Optimized `list_files()` - eliminated N+1 HTTP requests

#### Cloud Functions
- `call(function_name, data, region)` - Call Firebase Cloud Functions (callable)
- Automatic auth token inclusion
- Multi-region support

#### Realtime Database (RTDB)
- `get(path, default)` - Read data
- `set(path, data)` - Write/replace data
- `push(path, data)` - Add with auto-generated key
- `update(path, data)` - Update specific fields
- `delete(path)` - Delete data
- `stream(path, callback)` - Real-time streaming with SSE

### Changed
- Improved error handling across all modules
- Added complete type hints
- Unified version to 0.2.0

## [0.1.0] - Initial Release

### Added
- Basic Firebase REST API client
- Authentication (sign up, sign in, sign out)
- Firestore (CRUD operations)
- Storage (upload, download, list, delete)
- Support for Streamlit applications
- No admin credentials required

### Features
- Email/password authentication
- Firestore document operations
- Storage file operations
- Session management

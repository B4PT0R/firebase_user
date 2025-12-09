"""Custom exceptions for Firebase client."""


class FirebaseException(Exception):
    """Base exception for Firebase operations."""

    def __init__(self, message: str, *args):
        super().__init__(message, *args)
        self.message = message

    def __str__(self) -> str:
        return f"Error: {self.message}"


class AuthException(FirebaseException):
    """Authentication-related errors."""


class FirestoreException(FirebaseException):
    """Firestore-related errors."""


class StorageException(FirebaseException):
    """Storage-related errors."""


class FunctionsException(FirebaseException):
    """Cloud Functions-related errors."""


class RealtimeDatabaseException(FirebaseException):
    """Realtime Database-related errors."""

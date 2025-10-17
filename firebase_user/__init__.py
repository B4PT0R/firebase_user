"""Firebase client library for Streamlit applications."""

from .client import FirebaseClient
from .exceptions import FirebaseException

__version__ = "0.3.0"
__all__ = ["FirebaseClient", "FirebaseException"]

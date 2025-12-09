"""Authentication module for Firebase client."""

import json
from typing import TYPE_CHECKING, Dict, Any, Optional

from .exceptions import AuthException

if TYPE_CHECKING:
    from .client import FirebaseClient


class Auth:
    """Handle Firebase Authentication operations."""

    FIREBASE_REST_API = "https://identitytoolkit.googleapis.com/v1/accounts"
    FIREBASE_REST_IDP = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp"

    def __init__(self, client: 'FirebaseClient'):
        self.client = client

    def sign_in(self, email: str, password: str) -> None:
        """
        Authenticate a user using email and password.
        Updates client.user with idToken and refreshToken.
        """
        url = f"{self.FIREBASE_REST_API}:signInWithPassword?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"email": email, "password": password, "returnSecureToken": True})

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        try:
            self.client.user = response.json()
        except Exception as exc:
            raise AuthException("Failed to parse authentication response") from exc
        if self.client.verbose:
            print("User successfully authenticated.")

    def sign_in_with_oauth(
        self,
        provider_id: str,
        access_token: Optional[str] = None,
        id_token: Optional[str] = None,
        request_uri: str = "http://localhost"
    ) -> None:
        """
        Authenticate using an OAuth provider (Google/GitHub/Apple/...).
        Provide either access_token or id_token from the provider.
        """
        if not access_token and not id_token:
            raise AuthException("access_token or id_token required for OAuth sign-in.")

        post_body_parts = [f"providerId={provider_id}"]
        if access_token:
            post_body_parts.append(f"access_token={access_token}")
        if id_token:
            post_body_parts.append(f"id_token={id_token}")
        post_body = "&".join(post_body_parts)

        url = f"{self.FIREBASE_REST_IDP}?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({
            "postBody": post_body,
            "requestUri": request_uri,
            "returnSecureToken": True
        })

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        try:
            self.client.user = response.json()
        except Exception as exc:
            raise AuthException("Failed to parse OAuth authentication response") from exc
        if self.client.verbose:
            print(f"User authenticated with provider {provider_id}.")

    def sign_in_with_user_object(self, user: Dict[str, Any]) -> None:
        """Sign in using a previously authenticated user object."""
        if user and user.get('idToken') and user.get('refreshToken') and user.get('email') and self.is_valid(user['idToken']):
            self.client.user = user
            if self.client.verbose:
                print("Successfully signed in with user object.")
        else:
            raise AuthException("Invalid or expired user idToken.")

    def is_valid(self, idToken: Optional[str] = None) -> bool:
        """Check if the given idToken is still valid."""
        user_token = self.client.user.get('idToken') if self.client.user is not None else None
        idToken = idToken or user_token

        if not idToken:
            return False

        # Firebase endpoint for verifying the idToken
        verify_token_url = f"{self.FIREBASE_REST_API}:lookup?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"idToken": idToken})

        response = self.client._request(type='post', url=verify_token_url, headers=headers, data=data)

        # If the token is valid, Firebase will return the user details
        # If the token is invalid, Firebase will return an error
        return response.status_code == 200

    @property
    def authenticated(self) -> bool:
        """Check if the current user is authenticated with a valid token."""
        return (self.client.user is not None
                and self.client.user.get('idToken') is not None
                and self.client.user.get('refreshToken') is not None
                and self.client.user.get('email') is not None
                and self.is_valid())

    def refresh_token(self) -> None:
        """Refresh the user's idToken using the refreshToken."""
        if not self.client.user or not self.client.user.get('refreshToken'):
            raise AuthException("No refresh token available.")

        url = f"https://securetoken.googleapis.com/v1/token?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"grant_type": "refresh_token", "refresh_token": self.client.user['refreshToken']})

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        refresh = response.json()
        self.client.user['idToken'] = refresh['id_token']
        self.client.user['refreshToken'] = refresh['refresh_token']
        self.client.user['expiresIn'] = refresh['expires_in']
        if self.client.verbose:
            print("Token successfully refreshed.")

    def log_out(self) -> None:
        """Log out the current user."""
        self.client.user = None
        if self.client.verbose:
            print("User successfully logged out.")

    def sign_up(self, email: str, password: str) -> None:
        """
        Create a new user with email and password.
        Updates client.user with idToken and refreshToken.
        """
        url = f"{self.FIREBASE_REST_API}:signUp?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"email": email, "password": password, "returnSecureToken": True})

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        self.client.user = response.json()
        if self.client.verbose:
            print(f"New user successfully created: {self.client.user['email']}")

    def delete_user(self) -> None:
        """Delete the authenticated user from Firebase Authentication."""
        if not self.client.user or not self.client.user.get('idToken'):
            raise AuthException("No authenticated user to delete.")

        url = f"{self.FIREBASE_REST_API}:delete?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"idToken": self.client.user['idToken']})

        self.client._make_request(type='post', url=url, headers=headers, data=data)
        if self.client.verbose:
            print("User successfully deleted.")

    def change_password(self, new_password: str) -> None:
        """Update the password of the authenticated user."""
        if not self.client.user or not self.client.user.get('idToken'):
            raise AuthException("No authenticated user.")

        url = f"{self.FIREBASE_REST_API}:update?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"idToken": self.client.user['idToken'], "password": new_password, "returnSecureToken": True})

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        self.client.user = response.json()
        if self.client.verbose:
            print("Password changed.")

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get public user information (safe to display in UI).
        Excludes sensitive tokens and technical fields.

        Returns:
            Dictionary with: uid, email, emailVerified, displayName, photoUrl, createdAt, lastLoginAt
        """
        if not self.client.user or not self.client.user.get('idToken'):
            raise AuthException("No authenticated user.")

        url = f"{self.FIREBASE_REST_API}:lookup?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"idToken": self.client.user['idToken']})

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        user_data = response.json()['users'][0]

        # Return ONLY public data (no tokens)
        return {
            'uid': user_data.get('localId'),
            'email': user_data.get('email'),
            'emailVerified': user_data.get('emailVerified', False),
            'displayName': user_data.get('displayName'),
            'photoUrl': user_data.get('photoUrl'),
            'createdAt': user_data.get('createdAt'),
            'lastLoginAt': user_data.get('lastLoginAt'),
        }

    def restore_session(self, refresh_token: str) -> None:
        """
        Restore user session from a refresh token (e.g., from localStorage or session_state).
        Useful for maintaining authentication across page refreshes in Streamlit.

        :param refresh_token: The refresh token obtained from a previous authentication
        """
        url = f"https://securetoken.googleapis.com/v1/token?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"grant_type": "refresh_token", "refresh_token": refresh_token})

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        token_data = response.json()

        # Get user info with the new token
        self.client.user = {
            'idToken': token_data['id_token'],
            'refreshToken': token_data['refresh_token'],
            'expiresIn': token_data['expires_in']
        }

        # Fetch email and other user info
        user_info = self.get_user_info()
        self.client.user['email'] = user_info['email']
        self.client.user['localId'] = user_info['uid']

        if self.client.verbose:
            print(f"Session restored for {user_info['email']}")

    def send_password_reset_email(self, email: str) -> None:
        """
        Send a password reset email to the specified email address.
        Uses Firebase's built-in email service (free).

        :param email: Email address to send the reset link to
        """
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"requestType": "PASSWORD_RESET", "email": email})

        self.client._make_request(type='post', url=url, headers=headers, data=data)
        if self.client.verbose:
            print(f"Password reset email sent to {email}")

    def send_email_verification(self) -> None:
        """
        Send an email verification link to the authenticated user's email.
        Uses Firebase's built-in email service (free).
        """
        if not self.client.user or not self.client.user.get('idToken'):
            raise AuthException("No authenticated user.")

        url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"requestType": "VERIFY_EMAIL", "idToken": self.client.user['idToken']})

        self.client._make_request(type='post', url=url, headers=headers, data=data)
        if self.client.verbose:
            print("Verification email sent")

    def update_profile(self, display_name: Optional[str] = None, photo_url: Optional[str] = None) -> None:
        """
        Update user profile (display name and/or photo URL).

        :param display_name: New display name (None to keep current)
        :param photo_url: New photo URL (None to keep current)
        """
        if not self.client.user or not self.client.user.get('idToken'):
            raise AuthException("No authenticated user.")

        update_data: Dict[str, Any] = {"idToken": self.client.user['idToken'], "returnSecureToken": True}

        if display_name is not None:
            update_data['displayName'] = display_name
        if photo_url is not None:
            update_data['photoUrl'] = photo_url

        url = f"{self.FIREBASE_REST_API}:update?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps(update_data)

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        updated = response.json()

        # Preserve technical session fields that may be missing from the update response
        current = self.client.user or {}
        self.client.user = {
            **current,
            **updated,
            "email": current.get("email") or updated.get("email"),
            "refreshToken": current.get("refreshToken") or updated.get("refreshToken"),
        }
        if self.client.verbose:
            print("Profile updated successfully")

    def update_email(self, new_email: str) -> None:
        """Update the email of the authenticated user."""
        if not self.client.user or not self.client.user.get('idToken'):
            raise AuthException("No authenticated user.")

        url = f"{self.FIREBASE_REST_API}:update?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"idToken": self.client.user['idToken'], "email": new_email, "returnSecureToken": True})

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        self.client.user = response.json()
        if self.client.verbose:
            print("Email updated successfully")

    def link_provider(
        self,
        provider_id: str,
        access_token: Optional[str] = None,
        id_token: Optional[str] = None,
        request_uri: str = "http://localhost"
    ) -> None:
        """
        Link an OAuth provider to the current user.
        """
        if not self.client.user or not self.client.user.get('idToken'):
            raise AuthException("No authenticated user.")
        if not access_token and not id_token:
            raise AuthException("access_token or id_token required for linking provider.")

        post_body_parts = [f"providerId={provider_id}"]
        if access_token:
            post_body_parts.append(f"access_token={access_token}")
        if id_token:
            post_body_parts.append(f"id_token={id_token}")
        post_body = "&".join(post_body_parts)

        url = f"{self.FIREBASE_REST_IDP}?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({
            "idToken": self.client.user['idToken'],
            "postBody": post_body,
            "requestUri": request_uri,
            "returnSecureToken": True
        })

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        self.client.user = response.json()
        if self.client.verbose:
            print(f"Provider {provider_id} linked.")

    def unlink_provider(self, provider_ids: Any) -> None:
        """
        Unlink one or more providers from the current user.

        :param provider_ids: Single providerId or iterable of providerIds to unlink.
        """
        if not self.client.user or not self.client.user.get('idToken'):
            raise AuthException("No authenticated user.")

        if isinstance(provider_ids, str):
            provider_ids = [provider_ids]

        url = f"{self.FIREBASE_REST_API}:update?key={self.client.config['apiKey']}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({
            "idToken": self.client.user['idToken'],
            "deleteProvider": list(provider_ids),
            "returnSecureToken": True
        })

        response = self.client._make_request(type='post', url=url, headers=headers, data=data)
        self.client.user = response.json()
        if self.client.verbose:
            print(f"Providers {provider_ids} unlinked.")

    def get_refresh_token(self) -> Optional[str]:
        """Get the current user's refresh token for session persistence."""
        if self.client.user:
            return self.client.user.get('refreshToken')
        return None

    def to_session_dict(self) -> Dict[str, str]:
        """
        Export minimal session data for storage (e.g., in st.session_state or localStorage).
        Only includes refresh_token and email for session restoration.

        Returns:
            Dictionary with 'refresh_token' and 'email' (safe to store)
        """
        if not self.client.user:
            return {}

        return {
            'refresh_token': self.client.user.get('refreshToken', ''),
            'email': self.client.user.get('email', '')
        }

    def from_session_dict(self, session_data: Dict[str, str]) -> None:
        """
        Restore session from previously saved session data.

        :param session_data: Dictionary with 'refresh_token' key
        """
        refresh_token = session_data.get('refresh_token')
        if not refresh_token:
            raise AuthException("No refresh_token in session data")

        self.restore_session(refresh_token)

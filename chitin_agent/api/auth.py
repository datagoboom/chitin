"""Authentication middleware for API."""

import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class APIAuth:
    """Manages API authentication tokens."""

    def __init__(self, token_file: Optional[Path] = None):
        """
        Initialize API auth.

        Args:
            token_file: Path to token file (default: ~/.config/chitin/api_token)
        """
        if token_file is None:
            token_file = Path.home() / ".config" / "chitin" / "api_token"
        self.token_file = token_file
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self._token: Optional[str] = None

    def generate_token(self) -> str:
        """Generate a new random token."""
        token = secrets.token_urlsafe(32)
        self._token = token
        self.save_token(token)
        return token

    def load_token(self) -> Optional[str]:
        """Load token from file."""
        if self.token_file.exists():
            return self.token_file.read_text().strip()
        return None

    def save_token(self, token: str) -> None:
        """Save token to file."""
        self.token_file.write_text(token)

    def get_token(self) -> str:
        """Get current token, generating if needed."""
        if self._token:
            return self._token
        token = self.load_token()
        if not token:
            token = self.generate_token()
        self._token = token
        return token

    def verify_token(self, token: str) -> bool:
        """Verify a token matches the current token."""
        return token == self.get_token()


# Global auth instance
_auth = APIAuth()

# Security scheme
security = HTTPBearer()


def get_auth() -> APIAuth:
    """Get the global auth instance."""
    return _auth


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Verify bearer token from request.

    Raises:
        HTTPException: 401 if token is invalid or missing
    """
    token = credentials.credentials
    auth = get_auth()

    if not auth.verify_token(token):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token

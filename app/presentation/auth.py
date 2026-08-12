from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets


ROLES = {"viewer", "editor", "admin"}


class AuthenticationError(Exception):
    pass


class AuthorizationError(Exception):
    pass


@dataclass(frozen=True)
class User:
    username: str
    role: str


def hash_password(password: str, salt: bytes | None = None, iterations: int = 600_000) -> str:
    if not password:
        raise ValueError("password cannot be empty")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


class BasicAuthenticator:
    challenge = 'Basic realm="document-api"'

    def __init__(self, users_json: str | None):
        try:
            users = json.loads(users_json or "")
            self.users = {item["username"]: item for item in users}
            if not self.users or len(self.users) != len(users) or any(
                not isinstance(item.get("username"), str)
                or item.get("role") not in ROLES
                or not isinstance(item.get("password_hash"), str)
                for item in users
            ):
                raise ValueError
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise RuntimeError("AUTH_USERS_JSON must contain unique users with a password_hash and role") from exc

    def authenticate(self, authorization: str | None) -> User:
        try:
            scheme, token = (authorization or "").split(" ", 1)
            username, password = base64.b64decode(token, validate=True).decode().split(":", 1)
            record = self.users.get(username)
            if scheme.lower() != "basic" or not record or not verify_password(password, record["password_hash"]):
                raise ValueError
            return User(username, record["role"])
        except (binascii.Error, UnicodeDecodeError, ValueError):
            raise AuthenticationError("valid credentials are required")

    @staticmethod
    def authorize(user: User, method: str) -> None:
        if user.role == "viewer" and method != "GET":
            raise AuthorizationError("viewer role is read-only")
        if user.role == "editor" and method == "DELETE":
            raise AuthorizationError("editor role cannot delete documents")


class CognitoAuthenticator:
    """Authenticate Cognito access tokens and map one User Pool group to an API role."""

    challenge = "Bearer"

    def __init__(self, user_pool_id: str | None, client_id: str | None, region: str | None, client=None):
        if not user_pool_id or not client_id or not region:
            raise RuntimeError("COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, and AWS_REGION are required for AUTH_MODE=cognito")
        self.user_pool_id, self.client_id, self.region = user_pool_id, client_id, region
        if client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError("Install requirements.txt to use AUTH_MODE=cognito") from exc
            client = boto3.client("cognito-idp", region_name=region)
        self.client = client

    @staticmethod
    def _claims(token: str) -> dict:
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            if not isinstance(claims, dict):
                raise ValueError
            return claims
        except (IndexError, ValueError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
            raise AuthenticationError("valid Cognito access token required")

    def authenticate(self, authorization: str | None) -> User:
        try:
            scheme, token = (authorization or "").split(" ", 1)
            if scheme.lower() != "bearer" or not token:
                raise ValueError
            response = self.client.get_user(AccessToken=token)
        except ValueError:
            raise AuthenticationError("valid Cognito access token required")
        except Exception as exc:
            try:
                from botocore.exceptions import ClientError
            except ImportError:
                ClientError = ()
            if isinstance(exc, ClientError):
                raise AuthenticationError("valid Cognito access token required") from exc
            raise

        claims = self._claims(token)
        issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
        if claims.get("iss") != issuer or claims.get("client_id") != self.client_id or claims.get("token_use") != "access":
            raise AuthenticationError("valid Cognito access token required")
        roles = {group["GroupName"] for group in self.client.admin_list_groups_for_user(UserPoolId=self.user_pool_id, Username=response["Username"]).get("Groups", [])} & ROLES
        if len(roles) != 1:
            raise AuthenticationError("Cognito user must belong to exactly one API role group")
        return User(response["Username"], roles.pop())

    authorize = staticmethod(BasicAuthenticator.authorize)


def main():
    import getpass

    username = input("Username: ").strip()
    role = input("Role (viewer/editor/admin): ").strip()
    if role not in ROLES or not username:
        raise SystemExit("A username and role viewer, editor, or admin are required.")
    print(json.dumps({"username": username, "password_hash": hash_password(getpass.getpass()), "role": role}))


if __name__ == "__main__":
    main()

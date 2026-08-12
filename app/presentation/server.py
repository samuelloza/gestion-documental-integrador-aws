from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from pathlib import Path
from wsgiref.simple_server import make_server

from ..bootstrap import build_service
from ..config import Settings
from ..domain import ConflictError, NotFoundError
from .auth import AuthenticationError, AuthorizationError, BasicAuthenticator, CognitoAuthenticator


class ApiApplication:
    def __init__(self, service=None, static_dir: Path | None = None, authenticator: BasicAuthenticator | None = None, cors_origin: str | None = None):
        self.service = service or build_service()
        self.static_dir = static_dir or Path(__file__).resolve().parents[2] / "web"
        self.authenticator, self.cors_origin = authenticator, cors_origin

    def __call__(self, environ, start_response):
        def start(status, headers, exc_info=None):
            if self.cors_origin:
                headers += [("Access-Control-Allow-Origin", self.cors_origin), ("Access-Control-Allow-Headers", "Authorization, Content-Type"), ("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")]
            return start_response(status, headers) if exc_info is None else start_response(status, headers, exc_info)
        try:
            path, method = environ.get("PATH_INFO", "/"), environ["REQUEST_METHOD"]
            if method == "OPTIONS" and path.startswith("/api/"):
                start("204 No Content", [])
                return [b""]
            if path.startswith("/api/") and path != "/api/health":
                if not self.authenticator:
                    raise RuntimeError("API authentication is not configured")
                user = self.authenticator.authenticate(environ.get("HTTP_AUTHORIZATION"))
                self.authenticator.authorize(user, method)
                environ["document.user"] = user
            return self.dispatch(environ, start)
        except AuthenticationError as exc:
            return self.json(start, HTTPStatus.UNAUTHORIZED, {"error": str(exc)}, [("WWW-Authenticate", getattr(self.authenticator, "challenge", "Bearer"))])
        except AuthorizationError as exc:
            return self.json(start, HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except NotFoundError as exc:
            return self.json(start_response, HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except ConflictError as exc:
            return self.json(start_response, HTTPStatus.CONFLICT, {"error": str(exc)})
        except ValueError as exc:
            return self.json(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            return self.json(start_response, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal server error"})

    def dispatch(self, env, start):
        method, path = env["REQUEST_METHOD"], env.get("PATH_INFO", "/")
        parts = [part for part in path.split("/") if part]
        if not parts or parts[0] != "api":
            return self.static(start, path)
        if parts == ["api", "health"] and method == "GET":
            return self.json(start, HTTPStatus.OK, {"status": "ok"})
        if parts == ["api", "session"] and method == "GET":
            user = env["document.user"]
            return self.json(start, HTTPStatus.OK, {"username": user.username, "role": user.role})
        if parts == ["api", "documents"]:
            if method == "GET": return self.json(start, HTTPStatus.OK, {"items": [d.public() for d in self.service.list()]})
            if method == "POST": return self.json(start, HTTPStatus.CREATED, self.service.create(self.read_json(env)).public())
        if len(parts) == 3 and parts[:2] == ["api", "documents"]:
            identifier = parts[2]
            if method == "GET": return self.json(start, HTTPStatus.OK, self.service.get(identifier).public())
            if method == "PATCH": return self.json(start, HTTPStatus.OK, self.service.update(identifier, self.read_json(env)).public())
            if method == "DELETE": self.service.delete(identifier); return self.json(start, HTTPStatus.OK, {"deleted": identifier})
        if len(parts) == 4 and parts[:2] == ["api", "documents"] and parts[3] == "content" and method == "PUT":
            length = int(env.get("CONTENT_LENGTH") or 0)
            return self.json(start, HTTPStatus.OK, self.service.upload(parts[2], env["wsgi.input"].read(length), env.get("CONTENT_TYPE", "application/octet-stream")).public())
        if len(parts) == 4 and parts[:2] == ["api", "documents"] and parts[3] == "content" and method == "GET":
            url = self.service.signed_download(parts[2])
            if url:
                return self.json(start, HTTPStatus.OK, {"url": url, "expires_in": 300})
            doc, body = self.service.download(parts[2])
            return self.binary(start, body, doc.content_type or "application/octet-stream")
        return self.json(start, HTTPStatus.NOT_FOUND, {"error": "route not found"})

    @staticmethod
    def read_json(env):
        length = int(env.get("CONTENT_LENGTH") or 0)
        try:
            body = json.loads(env["wsgi.input"].read(length))
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
            return body
        except (json.JSONDecodeError, UnicodeDecodeError): raise ValueError("body must be valid JSON")

    @staticmethod
    def json(start, status, body, extra_headers=None):
        encoded = json.dumps(body).encode()
        start(f"{status.value} {status.phrase}", [("Content-Type", "application/json"), ("Content-Length", str(len(encoded)))] + (extra_headers or []))
        return [encoded]

    @staticmethod
    def binary(start, body, content_type):
        start("200 OK", [("Content-Type", content_type), ("Content-Length", str(len(body)))])
        return [body]

    def static(self, start, path):
        target = self.static_dir / ("index.html" if path == "/" else path.lstrip("/"))
        if not target.is_file() or self.static_dir not in target.resolve().parents and target.resolve() != self.static_dir:
            return self.json(start, HTTPStatus.NOT_FOUND, {"error": "not found"})
        body = target.read_bytes()
        start("200 OK", [("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream"), ("Content-Length", str(len(body)))])
        return [body]


def main():
    settings = Settings.from_env()
    if settings.auth_mode == "basic":
        authenticator = BasicAuthenticator(settings.auth_users_json)
    elif settings.auth_mode == "cognito":
        authenticator = CognitoAuthenticator(settings.cognito_user_pool_id, settings.cognito_client_id, settings.aws_region)
    else:
        raise RuntimeError("AUTH_MODE must be basic or cognito")
    with make_server(settings.bind_host, 8000, ApiApplication(build_service(settings), settings.static_dir, authenticator, settings.cors_origin)) as server:
        print(f"Serving on http://{settings.bind_host}:8000")
        server.serve_forever()


if __name__ == "__main__":
    main()

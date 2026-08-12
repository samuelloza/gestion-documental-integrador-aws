from __future__ import annotations

import io
import json
import os
import base64
import tempfile
import unittest
from pathlib import Path
from wsgiref.util import setup_testing_defaults

from app.bootstrap import build_service
from app.application import DocumentService
from app.infrastructure.repositories import SQLiteDocuments
from app.presentation.auth import AuthenticationError, BasicAuthenticator, CognitoAuthenticator, hash_password
from app.presentation.server import ApiApplication
from app.config import Settings
from app.seeds import seed_documents


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        settings = Settings(root, Path('web'), 'local', 'sqlite', None, 'documents', None, None)
        users = json.dumps([{'username': 'admin', 'password_hash': hash_password('test-password'), 'role': 'admin'}])
        self.app = ApiApplication(build_service(settings), Path(__file__).parents[1] / 'web', BasicAuthenticator(users))

    def tearDown(self): self.tmp.cleanup()

    def call(self, method, path, payload=b'', content_type='application/json', user='admin:test-password'):
        env = {}; setup_testing_defaults(env)
        env.update(REQUEST_METHOD=method, PATH_INFO=path, CONTENT_LENGTH=str(len(payload)), CONTENT_TYPE=content_type, HTTP_AUTHORIZATION=f'Basic {base64.b64encode(user.encode()).decode()}', **{'wsgi.input': io.BytesIO(payload)})
        captured = {}; result = b''.join(self.app(env, lambda status, headers: captured.update(status=status, headers=headers)))
        return int(captured['status'][:3]), json.loads(result)

    def call_body(self, method, path):
        env = {}; setup_testing_defaults(env)
        env.update(REQUEST_METHOD=method, PATH_INFO=path, CONTENT_LENGTH='0', HTTP_AUTHORIZATION='Basic YWRtaW46dGVzdC1wYXNzd29yZA==', **{'wsgi.input': io.BytesIO()})
        captured = {}; result = b''.join(self.app(env, lambda status, headers: captured.update(status=status, headers=dict(headers))))
        return int(captured['status'][:3]), captured['headers'], result

    def test_document_lifecycle(self):
        status, doc = self.call('POST', '/api/documents', b'{"folio":"F-1","name":"Contrato","document_type":"pdf"}')
        self.assertEqual(status, 201); identifier = doc['id']
        status, doc = self.call('PUT', f'/api/documents/{identifier}/content', b'PDF', 'application/pdf')
        self.assertEqual((status, doc['status'], doc['size_bytes']), (200, 'UPLOADED', 3))
        status, doc = self.call('PATCH', f'/api/documents/{identifier}', b'{"status":"ARCHIVED"}')
        self.assertEqual((status, doc['status']), (200, 'ARCHIVED'))
        status, docs = self.call('GET', '/api/documents')
        self.assertEqual((status, len(docs['items'])), (200, 1))
        status, _ = self.call('DELETE', f'/api/documents/{identifier}')
        self.assertEqual(status, 200)
        self.assertEqual(self.call('GET', f'/api/documents/{identifier}')[0], 404)

    def test_gets_local_document_content(self):
        _, doc = self.call('POST', '/api/documents', b'{"folio":"F-2","name":"Contrato","document_type":"pdf"}')
        self.call('PUT', f'/api/documents/{doc["id"]}/content', b'PDF', 'application/pdf')
        status, headers, body = self.call_body('GET', f'/api/documents/{doc["id"]}/content')
        self.assertEqual((status, headers['Content-Type'], body), (200, 'application/pdf', b'PDF'))

    def test_serves_the_protected_documents_page(self):
        status, headers, body = self.call_body('GET', '/documents.html')
        self.assertEqual((status, headers['Content-Type']), (200, 'text/html'))
        self.assertIn(b'<title>Documentos | Gesti', body)

    def test_rejects_duplicate_folio(self):
        payload = b'{"folio":"F-1","name":"Contrato","document_type":"pdf"}'
        self.call('POST', '/api/documents', payload)
        self.assertEqual(self.call('POST', '/api/documents', payload)[0], 409)

    def test_rejects_non_object_json(self):
        self.assertEqual(self.call('POST', '/api/documents', b'[]')[0], 400)

    def test_postgres_requires_a_database_url(self):
        settings = Settings(Path('.'), Path('web'), 'local', 'postgres', None, 'documents', None, None)
        with self.assertRaisesRegex(RuntimeError, 'DATABASE_URL'):
            build_service(settings)

    def test_settings_loads_database_url_from_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('DATABASE_URL=postgresql://user:secret@db.internal/documents\n')
            previous = os.environ.pop('DATABASE_URL', None)
            try:
                self.assertEqual(Settings.from_env(root).database_url, 'postgresql://user:secret@db.internal/documents')
            finally:
                if previous is not None:
                    os.environ['DATABASE_URL'] = previous

    def test_settings_loads_s3_from_local_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.local').write_text('STORAGE_BACKEND=s3\nS3_BUCKET=documents-local\nAWS_REGION=us-east-1\n')
            previous = {key: os.environ.pop(key, None) for key in ('STORAGE_BACKEND', 'S3_BUCKET', 'AWS_REGION')}
            try:
                settings = Settings.from_env(root)
                self.assertEqual((settings.storage_backend, settings.s3_bucket, settings.aws_region), ('s3', 'documents-local', 'us-east-1'))
            finally:
                for key, value in previous.items():
                    if value is not None:
                        os.environ[key] = value

    def test_seeds_are_idempotent(self):
        self.assertEqual(seed_documents(self.app.service), 3)
        self.assertEqual(seed_documents(self.app.service), 0)

    def test_s3_download_uses_a_signed_url(self):
        class SignedStorage:
            def put(self, key, body, content_type): pass
            def get(self, key): raise AssertionError('signed URL should be used')
            def signed_get(self, key, expires_in): return f'https://bucket.example/{key}?expires={expires_in}'
            def delete(self, key): pass

        service = DocumentService(SQLiteDocuments(Path(self.tmp.name) / 'signed.db'), SignedStorage(), 'documents')
        doc = service.create({'folio': 'F-3', 'name': 'Acta', 'document_type': 'pdf'})
        service.upload(doc.id, b'PDF', 'application/pdf')
        self.assertEqual(service.signed_download(doc.id), f'https://bucket.example/documents/{doc.id}?expires=300')

    def test_roles_protect_document_changes(self):
        users = json.dumps([{'username': 'reader', 'password_hash': hash_password('reader-password'), 'role': 'viewer'}])
        app = ApiApplication(self.app.service, authenticator=BasicAuthenticator(users))
        original, self.app = self.app, app
        try:
            self.assertEqual(self.call('POST', '/api/documents', b'{"folio":"F-4","name":"Acta","document_type":"pdf"}', user='reader:reader-password')[0], 403)
            self.assertEqual(self.call('GET', '/api/documents', user='reader:reader-password')[0], 200)
        finally:
            self.app = original

    def test_cognito_access_token_maps_its_group_to_an_api_role(self):
        class CognitoClient:
            def get_user(self, **kwargs): return {'Username': 'editor.demo'}
            def admin_list_groups_for_user(self, **kwargs):
                self.request = kwargs
                return {'Groups': [{'GroupName': 'editor'}]}

        def token(claims):
            payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=').decode()
            return f'header.{payload}.signature'

        client = CognitoClient()
        authenticator = CognitoAuthenticator('us-east-1_example', 'client-id', 'us-east-1', client)
        user = authenticator.authenticate(f'Bearer {token({"iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example", "client_id": "client-id", "token_use": "access"})}')
        self.assertEqual((user.username, user.role), ('editor.demo', 'editor'))
        self.assertEqual(client.request, {'UserPoolId': 'us-east-1_example', 'Username': 'editor.demo'})

    def test_cognito_rejects_a_token_for_another_app_client(self):
        class CognitoClient:
            def get_user(self, **kwargs): return {'Username': 'editor.demo'}
            def admin_list_groups_for_user(self, **kwargs): return {'Groups': [{'GroupName': 'editor'}]}

        payload = base64.urlsafe_b64encode(json.dumps({'iss': 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example', 'client_id': 'other-client', 'token_use': 'access'}).encode()).rstrip(b'=').decode()
        authenticator = CognitoAuthenticator('us-east-1_example', 'client-id', 'us-east-1', CognitoClient())
        with self.assertRaises(AuthenticationError):
            authenticator.authenticate(f'Bearer header.{payload}.signature')
        with self.assertRaises(AuthenticationError):
            authenticator.authenticate('Bearer header.!.signature')


if __name__ == '__main__': unittest.main()

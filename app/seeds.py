from __future__ import annotations

from .bootstrap import build_service
from .domain import ConflictError


SEED_DOCUMENTS = (
    {"folio": "SEED-001", "name": "Política documental", "document_type": "pdf", "status": "ACTIVE"},
    {"folio": "SEED-002", "name": "Contrato modelo", "document_type": "pdf", "status": "PENDING_UPLOAD"},
    {"folio": "SEED-003", "name": "Acta de recepción", "document_type": "pdf", "status": "ARCHIVED"},
)


def seed_documents(service) -> int:
    created = 0
    for document in SEED_DOCUMENTS:
        try:
            service.create(document)
            created += 1
        except ConflictError:
            pass
    return created


def main():
    print(f"Seeded {seed_documents(build_service())} documents")


if __name__ == "__main__":
    main()

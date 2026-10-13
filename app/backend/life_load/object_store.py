"""Backup object store contracts for P-INFRA.

The production object-store implementation is intentionally unavailable here.
Local/dev implementations store opaque encrypted payload bytes and enforce
checksum, namespace, soft-delete, and no-false-purge semantics.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from life_load.sqlite_core import utc_now_iso


class ObjectStoreError(RuntimeError):
    pass


class ChecksumMismatchError(ObjectStoreError):
    pass


class ObjectNotFoundError(ObjectStoreError):
    pass


class ObjectDeletedError(ObjectStoreError):
    pass


class ProductionObjectStoreNotConfigured(ObjectStoreError):
    pass


class ObjectStoreUnavailableError(ObjectStoreError):
    pass


class ObjectStoreCorruptionError(ObjectStoreError):
    pass


@dataclass(frozen=True)
class StoredObjectMetadata:
    object_id: str
    user_id: str
    namespace_id: str
    sha256: str
    size_bytes: int
    created_at: str
    deleted_at: str = ""
    idempotency_key: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "object_id": self.object_id,
            "user_id": self.user_id,
            "namespace_id": self.namespace_id,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "deleted_at": self.deleted_at,
            "idempotency_key": self.idempotency_key,
            "purge_implemented": False,
        }


class BackupObjectStore(Protocol):
    def put_object(
        self,
        *,
        user_id: str,
        namespace_id: str,
        object_id: str,
        payload: bytes,
        sha256: str,
        idempotency_key: str = "",
    ) -> StoredObjectMetadata: ...

    def get_object(self, *, user_id: str, object_id: str) -> bytes: ...

    def list_objects(self, *, user_id: str, namespace_id: str) -> list[StoredObjectMetadata]: ...

    def mark_deleted(self, *, user_id: str, object_id: str) -> StoredObjectMetadata: ...

    def delete_object(self, *, user_id: str, object_id: str) -> StoredObjectMetadata: ...

    def delete_all_for_user(self, *, user_id: str) -> int: ...

    def purge_object(self, *, user_id: str, object_id: str) -> dict[str, object]: ...

    def object_exists(self, *, user_id: str, object_id: str) -> bool: ...

    def get_object_metadata(self, *, user_id: str, object_id: str) -> StoredObjectMetadata: ...

    def verify_checksum(self, *, user_id: str, object_id: str) -> bool: ...


class MemoryObjectStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], tuple[StoredObjectMetadata, bytes]] = {}

    def put_object(
        self,
        *,
        user_id: str,
        namespace_id: str,
        object_id: str,
        payload: bytes,
        sha256: str,
        idempotency_key: str = "",
    ) -> StoredObjectMetadata:
        _verify_payload_checksum(payload, sha256)
        metadata = StoredObjectMetadata(
            object_id=object_id,
            user_id=user_id,
            namespace_id=namespace_id,
            sha256=sha256,
            size_bytes=len(payload),
            created_at=utc_now_iso(),
            idempotency_key=idempotency_key,
        )
        self._records[(user_id, object_id)] = (metadata, bytes(payload))
        return metadata

    def get_object(self, *, user_id: str, object_id: str) -> bytes:
        metadata, payload = self._require_record(user_id=user_id, object_id=object_id)
        if metadata.deleted_at:
            raise ObjectDeletedError("backup object is deleted")
        return payload

    def list_objects(self, *, user_id: str, namespace_id: str) -> list[StoredObjectMetadata]:
        return [
            metadata
            for (record_user_id, _object_id), (metadata, _payload) in sorted(self._records.items())
            if record_user_id == user_id and metadata.namespace_id == namespace_id and not metadata.deleted_at
        ]

    def mark_deleted(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        metadata, payload = self._require_record(user_id=user_id, object_id=object_id)
        if metadata.deleted_at:
            return metadata
        deleted = StoredObjectMetadata(
            object_id=metadata.object_id,
            user_id=metadata.user_id,
            namespace_id=metadata.namespace_id,
            sha256=metadata.sha256,
            size_bytes=metadata.size_bytes,
            created_at=metadata.created_at,
            deleted_at=utc_now_iso(),
            idempotency_key=metadata.idempotency_key,
        )
        self._records[(user_id, object_id)] = (deleted, payload)
        return deleted

    def delete_object(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        return self.mark_deleted(user_id=user_id, object_id=object_id)

    def delete_all_for_user(self, *, user_id: str) -> int:
        count = 0
        for record_user_id, object_id in list(self._records):
            if record_user_id == user_id:
                metadata, _payload = self._records[(record_user_id, object_id)]
                if not metadata.deleted_at:
                    self.mark_deleted(user_id=user_id, object_id=object_id)
                    count += 1
        return count

    def purge_object(self, *, user_id: str, object_id: str) -> dict[str, object]:
        self._require_record(user_id=user_id, object_id=object_id)
        return {"purge_implemented": False, "purged": False, "reason": "future_production_feature"}

    def object_exists(self, *, user_id: str, object_id: str) -> bool:
        return (user_id, object_id) in self._records

    def get_object_metadata(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        metadata, _payload = self._require_record(user_id=user_id, object_id=object_id)
        return metadata

    def verify_checksum(self, *, user_id: str, object_id: str) -> bool:
        metadata, payload = self._require_record(user_id=user_id, object_id=object_id)
        return hashlib.sha256(payload).hexdigest() == metadata.sha256

    def _require_record(self, *, user_id: str, object_id: str) -> tuple[StoredObjectMetadata, bytes]:
        record = self._records.get((user_id, object_id))
        if record is None:
            raise ObjectNotFoundError("backup object not found")
        return record


class SQLiteBlobObjectStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def put_object(
        self,
        *,
        user_id: str,
        namespace_id: str,
        object_id: str,
        payload: bytes,
        sha256: str,
        idempotency_key: str = "",
    ) -> StoredObjectMetadata:
        _verify_payload_checksum(payload, sha256)
        metadata = StoredObjectMetadata(
            object_id=object_id,
            user_id=user_id,
            namespace_id=namespace_id,
            sha256=sha256,
            size_bytes=len(payload),
            created_at=utc_now_iso(),
            idempotency_key=idempotency_key,
        )
        with self.connect() as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO backup_object_store(
                    object_id, user_id, namespace_id, payload, sha256, size_bytes,
                    created_at, deleted_at, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.object_id,
                    metadata.user_id,
                    metadata.namespace_id,
                    payload,
                    metadata.sha256,
                    metadata.size_bytes,
                    metadata.created_at,
                    metadata.deleted_at,
                    metadata.idempotency_key,
                ),
            )
        return metadata

    def get_object(self, *, user_id: str, object_id: str) -> bytes:
        row = self._require_row(user_id=user_id, object_id=object_id)
        if row["deleted_at"]:
            raise ObjectDeletedError("backup object is deleted")
        return bytes(row["payload"])

    def list_objects(self, *, user_id: str, namespace_id: str) -> list[StoredObjectMetadata]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM backup_object_store
                WHERE user_id = ? AND namespace_id = ? AND deleted_at = ''
                ORDER BY created_at ASC, object_id ASC
                """,
                (user_id, namespace_id),
            ).fetchall()
        return [_metadata_from_row(row) for row in rows]

    def mark_deleted(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        row = self._require_row(user_id=user_id, object_id=object_id)
        if row["deleted_at"]:
            return _metadata_from_row(row)
        deleted_at = utc_now_iso()
        with self.connect() as conn, conn:
            conn.execute(
                "UPDATE backup_object_store SET deleted_at = ? WHERE user_id = ? AND object_id = ?",
                (deleted_at, user_id, object_id),
            )
        return self.get_object_metadata(user_id=user_id, object_id=object_id)

    def delete_object(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        return self.mark_deleted(user_id=user_id, object_id=object_id)

    def delete_all_for_user(self, *, user_id: str) -> int:
        with self.connect() as conn, conn:
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM backup_object_store WHERE user_id = ? AND deleted_at = ''",
                    (user_id,),
                ).fetchone()[0]
            )
            conn.execute(
                "UPDATE backup_object_store SET deleted_at = ? WHERE user_id = ? AND deleted_at = ''",
                (utc_now_iso(), user_id),
            )
        return count

    def purge_object(self, *, user_id: str, object_id: str) -> dict[str, object]:
        self._require_row(user_id=user_id, object_id=object_id)
        return {"purge_implemented": False, "purged": False, "reason": "future_production_feature"}

    def object_exists(self, *, user_id: str, object_id: str) -> bool:
        with self.connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM backup_object_store WHERE user_id = ? AND object_id = ?",
                    (user_id, object_id),
                ).fetchone()
                is not None
            )

    def get_object_metadata(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        return _metadata_from_row(self._require_row(user_id=user_id, object_id=object_id))

    def verify_checksum(self, *, user_id: str, object_id: str) -> bool:
        row = self._require_row(user_id=user_id, object_id=object_id)
        return hashlib.sha256(bytes(row["payload"])).hexdigest() == str(row["sha256"])

    def _require_row(self, *, user_id: str, object_id: str) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM backup_object_store WHERE user_id = ? AND object_id = ?",
                (user_id, object_id),
            ).fetchone()
        if row is None:
            raise ObjectNotFoundError("backup object not found")
        return row

    def _migrate(self) -> None:
        with self.connect() as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS backup_object_store (
                    object_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    namespace_id TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT NOT NULL DEFAULT '',
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(user_id, object_id)
                )
                """
            )


class S3ObjectStore:
    def __init__(self, *, configured: bool = False) -> None:
        self.configured = configured

    def __getattr__(self, _name: str) -> object:
        raise ProductionObjectStoreNotConfigured("production object store is not configured")

    def readiness(self) -> dict[str, object]:
        return {
            "schema_version": "life_load_object_store_readiness_v1",
            "mode": "s3_placeholder",
            "configured": self.configured,
            "production_ready": False,
        }


@dataclass(frozen=True)
class S3CompatibleObjectStoreConfig:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    prefix: str = "life-load-pinfra-fixtures"
    region_name: str = "us-east-1"
    initialize_bucket: bool = False

    @classmethod
    def from_env(cls) -> "S3CompatibleObjectStoreConfig | None":
        endpoint = str(os.environ.get("MINIO_TEST_ENDPOINT") or "").strip()
        access_key = str(os.environ.get("MINIO_TEST_ACCESS_KEY") or "").strip()
        secret_key = str(os.environ.get("MINIO_TEST_SECRET_KEY") or "").strip()
        bucket = str(os.environ.get("MINIO_TEST_BUCKET") or "").strip()
        if not all((endpoint, access_key, secret_key, bucket)):
            return None
        return cls(
            endpoint_url=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            prefix=str(os.environ.get("MINIO_TEST_PREFIX") or "life-load-pinfra-fixtures").strip(),
            initialize_bucket=str(os.environ.get("MINIO_TEST_INIT_BUCKET") or "").strip().lower()
            in {"1", "true", "yes"},
        )

    def redacted_summary(self) -> dict[str, object]:
        return {
            "schema_version": "life_load_s3_compatible_object_store_config_v1",
            "mode": "minio",
            "endpoint_configured": bool(self.endpoint_url),
            "access_key_configured": bool(self.access_key),
            "secret_key_configured": bool(self.secret_key),
            "bucket": self.bucket,
            "prefix": self.prefix,
            "initialize_bucket": self.initialize_bucket,
            "production_ready": False,
        }


class S3CompatibleObjectStore:
    """Local/dev S3-compatible object-store rehearsal adapter.

    This adapter is intended for MinIO or another S3-compatible fixture
    endpoint. It imports boto3 lazily so the default test environment has no
    production cloud dependency. Payload bytes stay opaque; metadata carries
    only hashes, sizes, namespace, tombstone state, and idempotency labels.
    """

    def __init__(self, config: S3CompatibleObjectStoreConfig, *, client: Any | None = None) -> None:
        self.config = config
        self._client = client or self._new_client(config)
        self._failure_injections: dict[str, int] = {}
        if config.initialize_bucket:
            self.initialize_bucket_for_test()

    def initialize_bucket_for_test(self) -> dict[str, object]:
        try:
            self._client.head_bucket(Bucket=self.config.bucket)
            created = False
        except Exception:
            self._client.create_bucket(Bucket=self.config.bucket)
            created = True
        return {"ok": True, "bucket": self.config.bucket, "created": created, "local_dev_only": True}

    def readiness(self) -> dict[str, object]:
        return {
            "schema_version": "life_load_object_store_readiness_v1",
            "mode": "minio",
            "configured": True,
            "bucket": self.config.bucket,
            "prefix": self.config.prefix,
            "production_ready": False,
        }

    def inject_failure_for_test(self, operation: str, *, count: int = 1) -> dict[str, object]:
        normalized = _safe_operation(operation)
        if normalized not in {"put", "get", "list", "delete"}:
            raise ValueError("unsupported object-store failure operation")
        self._failure_injections[normalized] = self._failure_injections.get(normalized, 0) + max(1, int(count))
        return {"ok": True, "operation": normalized, "remaining": self._failure_injections[normalized]}

    def put_object(
        self,
        *,
        user_id: str,
        namespace_id: str,
        object_id: str,
        payload: bytes,
        sha256: str,
        idempotency_key: str = "",
    ) -> StoredObjectMetadata:
        self._consume_failure("put")
        _verify_payload_checksum(payload, sha256)
        metadata = StoredObjectMetadata(
            object_id=object_id,
            user_id=user_id,
            namespace_id=namespace_id,
            sha256=sha256,
            size_bytes=len(payload),
            created_at=utc_now_iso(),
            idempotency_key=idempotency_key,
        )
        try:
            self._client.put_object(
                Bucket=self.config.bucket,
                Key=self._key(user_id, object_id),
                Body=bytes(payload),
                Metadata=self._s3_metadata(metadata),
            )
        except Exception as exc:
            raise ObjectStoreUnavailableError("object store put failed") from exc
        return metadata

    def get_object(self, *, user_id: str, object_id: str) -> bytes:
        self._consume_failure("get")
        try:
            result = self._client.get_object(Bucket=self.config.bucket, Key=self._key(user_id, object_id))
            metadata = self._metadata_from_s3(user_id=user_id, object_id=object_id, response=result)
            if metadata.deleted_at:
                raise ObjectDeletedError("backup object is deleted")
            payload = result["Body"].read()
        except ObjectDeletedError:
            raise
        except Exception as exc:
            raise ObjectNotFoundError("backup object not found") from exc
        if hashlib.sha256(payload).hexdigest() != metadata.sha256:
            raise ObjectStoreCorruptionError("backup object checksum mismatch")
        return payload

    def list_objects(self, *, user_id: str, namespace_id: str) -> list[StoredObjectMetadata]:
        self._consume_failure("list")
        try:
            response = self._client.list_objects_v2(Bucket=self.config.bucket, Prefix=self._user_prefix(user_id))
        except Exception as exc:
            raise ObjectStoreUnavailableError("object store list failed") from exc
        items: list[StoredObjectMetadata] = []
        for item in response.get("Contents", []) or []:
            key = str(item.get("Key") or "")
            object_id = key.rsplit("/", 1)[-1]
            try:
                head = self._client.head_object(Bucket=self.config.bucket, Key=key)
                metadata = self._metadata_from_s3(user_id=user_id, object_id=object_id, response=head)
            except Exception as exc:
                raise ObjectStoreUnavailableError("object store metadata read failed") from exc
            if metadata.namespace_id == namespace_id and not metadata.deleted_at:
                items.append(metadata)
        return sorted(items, key=lambda metadata: (metadata.created_at, metadata.object_id))

    def mark_deleted(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        self._consume_failure("delete")
        metadata = self.get_object_metadata(user_id=user_id, object_id=object_id)
        if metadata.deleted_at:
            return metadata
        deleted = StoredObjectMetadata(
            object_id=metadata.object_id,
            user_id=metadata.user_id,
            namespace_id=metadata.namespace_id,
            sha256=metadata.sha256,
            size_bytes=metadata.size_bytes,
            created_at=metadata.created_at,
            deleted_at=utc_now_iso(),
            idempotency_key=metadata.idempotency_key,
        )
        try:
            self._client.copy_object(
                Bucket=self.config.bucket,
                Key=self._key(user_id, object_id),
                CopySource={"Bucket": self.config.bucket, "Key": self._key(user_id, object_id)},
                Metadata=self._s3_metadata(deleted),
                MetadataDirective="REPLACE",
            )
        except Exception as exc:
            raise ObjectStoreUnavailableError("object store delete marker failed") from exc
        return deleted

    def delete_object(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        return self.mark_deleted(user_id=user_id, object_id=object_id)

    def delete_all_for_user(self, *, user_id: str) -> int:
        count = 0
        response = self._client.list_objects_v2(Bucket=self.config.bucket, Prefix=self._user_prefix(user_id))
        for item in response.get("Contents", []) or []:
            object_id = str(item.get("Key") or "").rsplit("/", 1)[-1]
            metadata = self.get_object_metadata(user_id=user_id, object_id=object_id)
            if not metadata.deleted_at:
                self.mark_deleted(user_id=user_id, object_id=object_id)
                count += 1
        return count

    def purge_object(self, *, user_id: str, object_id: str) -> dict[str, object]:
        self.get_object_metadata(user_id=user_id, object_id=object_id)
        return {"purge_implemented": False, "purged": False, "reason": "future_production_feature"}

    def object_exists(self, *, user_id: str, object_id: str) -> bool:
        try:
            self._client.head_object(Bucket=self.config.bucket, Key=self._key(user_id, object_id))
            return True
        except Exception:
            return False

    def get_object_metadata(self, *, user_id: str, object_id: str) -> StoredObjectMetadata:
        try:
            response = self._client.head_object(Bucket=self.config.bucket, Key=self._key(user_id, object_id))
        except Exception as exc:
            raise ObjectNotFoundError("backup object not found") from exc
        return self._metadata_from_s3(user_id=user_id, object_id=object_id, response=response)

    def verify_checksum(self, *, user_id: str, object_id: str) -> bool:
        try:
            payload = self.get_object(user_id=user_id, object_id=object_id)
            metadata = self.get_object_metadata(user_id=user_id, object_id=object_id)
        except ObjectStoreError:
            return False
        return hashlib.sha256(payload).hexdigest() == metadata.sha256

    def _consume_failure(self, operation: str) -> None:
        remaining = self._failure_injections.get(operation, 0)
        if remaining <= 0:
            return
        self._failure_injections[operation] = remaining - 1
        raise ObjectStoreUnavailableError("object store unavailable")

    def _key(self, user_id: str, object_id: str) -> str:
        return f"{self._user_prefix(user_id)}{_safe_key_segment(object_id)}"

    def _user_prefix(self, user_id: str) -> str:
        return f"{_safe_key_segment(self.config.prefix)}/{_safe_key_segment(user_id)}/"

    def _s3_metadata(self, metadata: StoredObjectMetadata) -> dict[str, str]:
        return {
            "life-load-user-id": metadata.user_id,
            "life-load-namespace-id": metadata.namespace_id,
            "life-load-object-id": metadata.object_id,
            "life-load-sha256": metadata.sha256,
            "life-load-size-bytes": str(metadata.size_bytes),
            "life-load-created-at": metadata.created_at,
            "life-load-deleted-at": metadata.deleted_at,
            "life-load-idempotency-key": metadata.idempotency_key,
        }

    def _metadata_from_s3(self, *, user_id: str, object_id: str, response: dict[str, Any]) -> StoredObjectMetadata:
        values = {str(key).lower(): str(value) for key, value in dict(response.get("Metadata") or {}).items()}
        if values.get("life-load-user-id") != user_id:
            raise PermissionError("object metadata user mismatch")
        size = int(values.get("life-load-size-bytes") or response.get("ContentLength") or 0)
        return StoredObjectMetadata(
            object_id=values.get("life-load-object-id") or object_id,
            user_id=user_id,
            namespace_id=values.get("life-load-namespace-id") or "",
            sha256=values.get("life-load-sha256") or "",
            size_bytes=size,
            created_at=values.get("life-load-created-at") or "",
            deleted_at=values.get("life-load-deleted-at") or "",
            idempotency_key=values.get("life-load-idempotency-key") or "",
        )

    def _new_client(self, config: S3CompatibleObjectStoreConfig) -> Any:
        try:
            import boto3  # type: ignore[import-not-found]
        except Exception as exc:
            raise ProductionObjectStoreNotConfigured("boto3 is required for MinIO/S3-compatible rehearsal") from exc
        return boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region_name,
        )


def object_store_from_environment(*, sqlite_path: Path | None = None) -> BackupObjectStore:
    mode = str(os.environ.get("LIFE_LOAD_OBJECT_STORE_MODE") or "sqlite").strip().lower()
    if mode == "memory":
        return MemoryObjectStore()
    if mode in {"sqlite", "local_file"}:
        return SQLiteBlobObjectStore(sqlite_path or Path("runtime/state/life_load_remote/object_store.sqlite"))
    if mode == "minio":
        config = S3CompatibleObjectStoreConfig.from_env()
        if config is None:
            raise ProductionObjectStoreNotConfigured("MINIO_TEST_* environment is not configured")
        return S3CompatibleObjectStore(config)
    raise ValueError("unsupported LIFE_LOAD_OBJECT_STORE_MODE")


def _verify_payload_checksum(payload: bytes, expected_sha256: str) -> None:
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise ChecksumMismatchError("backup object checksum mismatch")


def _metadata_from_row(row: sqlite3.Row) -> StoredObjectMetadata:
    return StoredObjectMetadata(
        object_id=str(row["object_id"]),
        user_id=str(row["user_id"]),
        namespace_id=str(row["namespace_id"]),
        sha256=str(row["sha256"]),
        size_bytes=int(row["size_bytes"]),
        created_at=str(row["created_at"]),
        deleted_at=str(row["deleted_at"] or ""),
        idempotency_key=str(row["idempotency_key"] or ""),
    )


def _safe_key_segment(value: str) -> str:
    text = str(value or "").strip()
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)[:160] or "blank"


def _safe_operation(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in str(value or "").strip().lower())

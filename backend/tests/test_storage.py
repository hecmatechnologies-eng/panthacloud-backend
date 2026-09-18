"""Unit tests for object storage providers (Local and Cloudflare R2)."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.storage import (
    LocalStorageProvider,
    R2StorageProvider,
    StorageError,
    StorageNotFoundError,
    get_storage_provider,
    set_storage_provider,
)


@pytest.mark.asyncio
async def test_local_storage_lifecycle(tmp_path):
    provider = LocalStorageProvider(base_dir=tmp_path)
    test_key = "test/documents/sample.txt"
    test_data = b"Hello Fussion Knowledge Storage!"

    # 1. Upload
    ref = await provider.upload(test_key, test_data, content_type="text/plain")
    assert ref.startswith("local://")
    assert await provider.exists(test_key) is True

    # 2. Download
    downloaded = await provider.download(test_key)
    assert downloaded == test_data

    # 3. Get URL
    url = await provider.get_url(test_key)
    assert f"/api/v1/storage/files/{test_key}" in url

    # 4. Delete
    await provider.delete(test_key)
    assert await provider.exists(test_key) is False

    # 5. Download after delete raises StorageNotFoundError
    with pytest.raises(StorageNotFoundError):
        await provider.download(test_key)

    # 6. Delete again is idempotent
    await provider.delete(test_key)


@pytest.mark.asyncio
async def test_local_storage_path_traversal_prevention(tmp_path):
    provider = LocalStorageProvider(base_dir=tmp_path)
    malicious_key = "../../etc/passwd"

    with pytest.raises(StorageError) as exc_info:
        await provider.upload(malicious_key, b"evil", "text/plain")
    assert "Path traversal detected" in str(exc_info.value)

    with pytest.raises(StorageError):
        await provider.download(malicious_key)


@pytest.mark.asyncio
async def test_r2_storage_provider_lifecycle():
    provider = R2StorageProvider(
        account_id="test-account-id-12345",
        access_key_id="test-access-key",
        secret_access_key="test-secret-key",
        bucket_name="test-bucket",
        endpoint_url="https://test-account-id-12345.r2.cloudflarestorage.com",
    )

    mock_s3 = MagicMock()
    provider._s3 = mock_s3

    # 1. Upload
    mock_s3.put_object.return_value = {}
    ref = await provider.upload("doc/1/test.pdf", b"%PDF-test", "application/pdf", {"doc_id": "1"})
    assert ref == "r2://test-bucket/doc/1/test.pdf"
    mock_s3.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="doc/1/test.pdf",
        Body=b"%PDF-test",
        ContentType="application/pdf",
        Metadata={"doc_id": "1"},
    )

    # 2. Download
    mock_body = MagicMock()
    mock_body.read.return_value = b"%PDF-test"
    mock_s3.get_object.return_value = {"Body": mock_body}
    data = await provider.download("doc/1/test.pdf")
    assert data == b"%PDF-test"
    mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="doc/1/test.pdf")

    # 3. Exists
    mock_s3.head_object.return_value = {}
    assert await provider.exists("doc/1/test.pdf") is True

    # 4. Get URL (presigned)
    mock_s3.generate_presigned_url.return_value = "https://presigned.r2.cloudflarestorage.com/download"
    url = await provider.get_url("doc/1/test.pdf", expires_in=1800)
    assert url == "https://presigned.r2.cloudflarestorage.com/download"
    mock_s3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "doc/1/test.pdf"},
        ExpiresIn=1800,
    )

    # 5. Delete
    mock_s3.delete_object.return_value = {}
    await provider.delete("doc/1/test.pdf")
    mock_s3.delete_object.assert_called_once_with(Bucket="test-bucket", Key="doc/1/test.pdf")


@pytest.mark.asyncio
async def test_r2_storage_not_found_handling():
    provider = R2StorageProvider(
        account_id="test-account-id",
        access_key_id="test-key",
        secret_access_key="test-secret",
        bucket_name="test-bucket",
    )
    mock_s3 = MagicMock()
    provider._s3 = mock_s3

    err_response = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
    mock_s3.get_object.side_effect = ClientError(err_response, "GetObject")

    with pytest.raises(StorageNotFoundError):
        await provider.download("nonexistent.txt")

    mock_s3.head_object.side_effect = ClientError(err_response, "HeadObject")
    assert await provider.exists("nonexistent.txt") is False


def test_storage_provider_factory_and_override():
    set_storage_provider(None)
    # When R2 credentials are not set -> LocalStorageProvider
    with patch("app.services.storage.settings.R2_ACCESS_KEY_ID", ""):
        set_storage_provider(None)
        default_provider = get_storage_provider()
        assert isinstance(default_provider, LocalStorageProvider)

    # When R2 credentials are set -> R2StorageProvider
    with patch("app.services.storage.settings.R2_ACCOUNT_ID", "acc"), \
         patch("app.services.storage.settings.R2_ACCESS_KEY_ID", "key"), \
         patch("app.services.storage.settings.R2_SECRET_ACCESS_KEY", "secret"), \
         patch("app.services.storage.settings.R2_BUCKET_NAME", "bucket"):
        set_storage_provider(None)
        r2_prov = get_storage_provider()
        assert isinstance(r2_prov, R2StorageProvider)

    # Test override
    mock_provider = MagicMock()
    set_storage_provider(mock_provider)
    assert get_storage_provider() is mock_provider
    set_storage_provider(None)

    # Reset
    set_storage_provider(None)

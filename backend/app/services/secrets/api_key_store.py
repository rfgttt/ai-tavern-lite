from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4


_FILE_MAGIC = b"AITL-DPAPI-KEY-V1\x00"
_DPAPI_ENTROPY = b"AI-Tavern-Lite/api-key/v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class ApiKeyStorageError(RuntimeError):
    """Raised when the API key cannot be stored or read safely."""


class SecretProtector(Protocol):
    def protect(self, plaintext: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


class ApiKeyStore(Protocol):
    available: bool
    backend_name: str

    def is_configured(self) -> bool: ...

    def read(self) -> str: ...

    def write(self, value: str) -> None: ...

    def clear(self) -> None: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WindowsDpapiProtector:
    """Protect data with the current Windows user's DPAPI profile."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise ApiKeyStorageError("Windows DPAPI 仅在 Windows 上可用")
        self._crypt32 = ctypes.windll.crypt32
        self._kernel32 = ctypes.windll.kernel32
        self._crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

    @staticmethod
    def _input_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(data)
        pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        return _DataBlob(len(data), pointer), buffer

    def protect(self, plaintext: bytes) -> bytes:
        input_blob, input_buffer = self._input_blob(plaintext)
        entropy_blob, entropy_buffer = self._input_blob(_DPAPI_ENTROPY)
        output_blob = _DataBlob()
        _ = (input_buffer, entropy_buffer)
        success = self._crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "AI Tavern Lite API Key",
            ctypes.byref(entropy_blob),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        if not success:
            raise ApiKeyStorageError("Windows DPAPI 加密 API Key 失败")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            self._kernel32.LocalFree(output_blob.pbData)

    def unprotect(self, ciphertext: bytes) -> bytes:
        input_blob, input_buffer = self._input_blob(ciphertext)
        entropy_blob, entropy_buffer = self._input_blob(_DPAPI_ENTROPY)
        output_blob = _DataBlob()
        _ = (input_buffer, entropy_buffer)
        success = self._crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        if not success:
            raise ApiKeyStorageError(
                "API Key 无法用当前 Windows 用户解密；请在设置中清除后重新保存"
            )
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            self._kernel32.LocalFree(output_blob.pbData)


class FileApiKeyStore:
    """Store one encrypted API key in an atomically replaced local file."""

    available = True
    backend_name = "windows_dpapi"

    def __init__(self, path: Path, protector: SecretProtector) -> None:
        self.path = Path(path).expanduser()
        self.protector = protector

    def is_configured(self) -> bool:
        return self.path.is_file()

    def _validate_existing_path(self) -> None:
        if self.path.is_symlink():
            raise ApiKeyStorageError("API Key 安全存储路径不能是符号链接")
        if self.path.exists() and not self.path.is_file():
            raise ApiKeyStorageError("API Key 安全存储路径不是普通文件")

    def read(self) -> str:
        self._validate_existing_path()
        if not self.path.exists():
            return ""
        try:
            payload = self.path.read_bytes()
        except OSError as error:
            raise ApiKeyStorageError("无法读取 API Key 安全存储文件") from error
        if not payload.startswith(_FILE_MAGIC):
            raise ApiKeyStorageError(
                "API Key 安全存储格式无效；请在设置中清除后重新保存"
            )
        ciphertext = payload[len(_FILE_MAGIC):]
        if not ciphertext:
            raise ApiKeyStorageError(
                "API Key 安全存储内容为空；请在设置中清除后重新保存"
            )
        try:
            plaintext = self.protector.unprotect(ciphertext)
            value = plaintext.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiKeyStorageError(
                "API Key 安全存储内容损坏；请在设置中清除后重新保存"
            ) from error
        if not value:
            raise ApiKeyStorageError(
                "API Key 安全存储内容为空；请在设置中清除后重新保存"
            )
        return value

    def write(self, value: str) -> None:
        normalized = str(value or "")
        if not normalized:
            self.clear()
            return
        self._validate_existing_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            ciphertext = self.protector.protect(normalized.encode("utf-8"))
        except ApiKeyStorageError:
            raise
        except Exception as error:
            raise ApiKeyStorageError("加密 API Key 失败") from error
        if not ciphertext:
            raise ApiKeyStorageError("加密 API Key 失败：加密结果为空")

        temp_path = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            descriptor = os.open(
                temp_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_FILE_MAGIC)
                handle.write(ciphertext)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, self.path)
        except Exception as error:
            temp_path.unlink(missing_ok=True)
            if isinstance(error, ApiKeyStorageError):
                raise
            raise ApiKeyStorageError("保存 API Key 安全存储文件失败") from error

    def clear(self) -> None:
        self._validate_existing_path()
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            raise ApiKeyStorageError("清除 API Key 安全存储文件失败") from error


class UnavailableApiKeyStore:
    """Compatibility store for non-Windows runtimes."""

    available = False
    backend_name = "database_legacy"

    def is_configured(self) -> bool:
        return False

    def read(self) -> str:
        return ""

    def write(self, value: str) -> None:
        raise ApiKeyStorageError("当前系统不支持 Windows DPAPI")

    def clear(self) -> None:
        return


def create_api_key_store(path: Path) -> ApiKeyStore:
    if os.name != "nt":
        return UnavailableApiKeyStore()
    return FileApiKeyStore(path, WindowsDpapiProtector())

# SPDX-License-Identifier: MIT

"""API key storage. Windows Credential Manager, with session-only fallback.

Never writes the key to JSON, git, or .kra files.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_TARGET = "krita-ai-art-assistant/openai-api-key"
_session_key = None

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
CRED_PERSIST_SESSION = 1


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _advapi32():
    dll = ctypes.WinDLL("advapi32", use_last_error=True)
    dll.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wintypes.DWORD]
    dll.CredWriteW.restype = wintypes.BOOL
    dll.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIAL)),
    ]
    dll.CredReadW.restype = wintypes.BOOL
    dll.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    dll.CredDeleteW.restype = wintypes.BOOL
    dll.CredFree.argtypes = [ctypes.c_void_p]
    dll.CredFree.restype = None
    return dll


def _windows_write(secret: str) -> None:
    blob = secret.encode("utf-8")
    blob_array = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    cred = _CREDENTIAL()
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = _TARGET
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(blob_array, ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = "openai"
    if not _advapi32().CredWriteW(ctypes.byref(cred), 0):
        raise OSError(ctypes.get_last_error())


def _windows_read() -> str | None:
    ptr = ctypes.POINTER(_CREDENTIAL)()
    dll = _advapi32()
    if not dll.CredReadW(_TARGET, CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
        return None
    try:
        cred = ptr.contents
        size = cred.CredentialBlobSize
        if not cred.CredentialBlob or size <= 0:
            return None
        raw = bytes(cred.CredentialBlob[i] for i in range(size))
        return raw.decode("utf-8")
    finally:
        dll.CredFree(ptr)


def _windows_delete() -> None:
    _advapi32().CredDeleteW(_TARGET, CRED_TYPE_GENERIC, 0)


def save_api_key(secret: str, persist: bool = True) -> str:
    """Return 'credential_manager' or 'session'."""
    global _session_key
    key = (secret or "").strip()
    if not key:
        raise ValueError("Paste an API key first.")
    if persist and sys.platform == "win32":
        try:
            _windows_write(key)
            _session_key = None
            return "credential_manager"
        except OSError:
            _session_key = key
            return "session"
    _session_key = key
    return "session"


def load_api_key() -> str:
    global _session_key
    if _session_key:
        return _session_key
    if sys.platform == "win32":
        try:
            stored = _windows_read()
            if stored:
                return stored
        except OSError:
            pass
    return ""


def clear_api_key() -> None:
    global _session_key
    _session_key = None
    if sys.platform == "win32":
        try:
            _windows_delete()
        except OSError:
            pass


def has_api_key() -> bool:
    return bool(load_api_key())

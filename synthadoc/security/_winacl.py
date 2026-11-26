# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Windows directory ACLs by the current user's SID (ctypes, no pywin32).

``restrict_to_current_user`` replaces a directory's DACL with ONE inheritable
allow-entry for the current user and marks it protected (no inherited entries),
then ``verify_current_user_only`` reads it back. Granting by SID works for local,
domain and Microsoft accounts and in any locale; ``icacls`` with a user name does
not. Windows-only: importing the module elsewhere is harmless, calling it is not.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes as wt

_IS_WINDOWS = sys.platform == "win32"

TOKEN_QUERY = 0x0008
TOKEN_USER = 1
ACL_REVISION = 2
ACL_SIZE_INFORMATION = 2
SE_FILE_OBJECT = 1
OWNER_SECURITY_INFORMATION = 0x1
DACL_SECURITY_INFORMATION = 0x4
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
SE_DACL_PROTECTED = 0x1000
OBJECT_INHERIT_ACE = 0x1
CONTAINER_INHERIT_ACE = 0x2
FILE_ALL_ACCESS = 0x1F01FF
ACCESS_ALLOWED_ACE_TYPE = 0

if _IS_WINDOWS:  # pragma: no branch
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.GetCurrentProcess.restype = wt.HANDLE
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    _advapi32.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
    _advapi32.OpenProcessToken.restype = wt.BOOL
    _advapi32.GetTokenInformation.argtypes = [
        wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    _advapi32.GetTokenInformation.restype = wt.BOOL
    _advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
    _advapi32.GetLengthSid.restype = wt.DWORD
    _advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _advapi32.EqualSid.restype = wt.BOOL
    _advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, wt.DWORD, wt.DWORD]
    _advapi32.InitializeAcl.restype = wt.BOOL
    _advapi32.AddAccessAllowedAceEx.argtypes = [
        ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_void_p]
    _advapi32.AddAccessAllowedAceEx.restype = wt.BOOL
    _advapi32.SetNamedSecurityInfoW.argtypes = [
        wt.LPWSTR, ctypes.c_int, wt.DWORD, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p]
    _advapi32.SetNamedSecurityInfoW.restype = wt.DWORD
    _advapi32.GetNamedSecurityInfoW.argtypes = [
        wt.LPWSTR, ctypes.c_int, wt.DWORD, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.GetNamedSecurityInfoW.restype = wt.DWORD
    _advapi32.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wt.WORD), ctypes.POINTER(wt.DWORD)]
    _advapi32.GetSecurityDescriptorControl.restype = wt.BOOL
    _advapi32.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.c_int]
    _advapi32.GetAclInformation.restype = wt.BOOL
    _advapi32.GetAce.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.GetAce.restype = wt.BOOL


class AclError(OSError):
    """The ACL could not be set or verified (callers fail closed)."""


class _AclSizeInformation(ctypes.Structure):
    _fields_ = [("AceCount", wt.DWORD), ("AclBytesInUse", wt.DWORD), ("AclBytesFree", wt.DWORD)]


def _require_windows() -> None:
    if not _IS_WINDOWS:
        raise AclError("Windows ACL helper called on a non-Windows platform")


def current_user_sid() -> bytes:
    """The current process user's SID as raw bytes."""
    _require_windows()
    token = wt.HANDLE()
    if not _advapi32.OpenProcessToken(_kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise AclError(f"OpenProcessToken failed ({ctypes.get_last_error()})")
    try:
        needed = wt.DWORD(0)
        _advapi32.GetTokenInformation(token, TOKEN_USER, None, 0, ctypes.byref(needed))
        buf = ctypes.create_string_buffer(needed.value)
        if not _advapi32.GetTokenInformation(token, TOKEN_USER, buf, needed, ctypes.byref(needed)):
            raise AclError(f"GetTokenInformation failed ({ctypes.get_last_error()})")
        # TOKEN_USER begins with SID_AND_ATTRIBUTES { PSID Sid; DWORD Attributes }.
        sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p)).contents.value
        length = _advapi32.GetLengthSid(sid_ptr)
        return ctypes.string_at(sid_ptr, length)
    finally:
        _kernel32.CloseHandle(token)


def _owner_sid(path: str) -> bytes:
    """The SID that owns *path*, as raw bytes."""
    _require_windows()
    owner = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    rc = _advapi32.GetNamedSecurityInfoW(
        path, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION, ctypes.byref(owner), None,
        None, None, ctypes.byref(descriptor))
    if rc != 0:
        raise AclError(f"GetNamedSecurityInfoW (owner) failed ({rc})")
    try:
        if not owner.value:
            raise AclError("directory has no owner")
        return ctypes.string_at(owner.value, _advapi32.GetLengthSid(owner.value))
    finally:
        if descriptor.value:
            _kernel32.LocalFree(descriptor)


def restrict_to_current_user(path: str) -> None:
    """Replace the DACL of *path* with a single inheritable full-control entry for the user,
    and make the user its owner (an elevated process creates folders owned by the
    Administrators group; an owner can rewrite the ACL at will, so it must be the user)."""
    _require_windows()
    sid = current_user_sid()
    sid_buf = ctypes.create_string_buffer(sid, len(sid))
    # ACL header (8) + ACCESS_ALLOWED_ACE without its SID (8, includes the 4-byte SidStart) - 4 + SID
    acl_size = (8 + 8 + len(sid) + 3) & ~3
    acl = ctypes.create_string_buffer(acl_size)
    if not _advapi32.InitializeAcl(acl, acl_size, ACL_REVISION):
        raise AclError(f"InitializeAcl failed ({ctypes.get_last_error()})")
    if not _advapi32.AddAccessAllowedAceEx(
            acl, ACL_REVISION, OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE, FILE_ALL_ACCESS, sid_buf):
        raise AclError(f"AddAccessAllowedAceEx failed ({ctypes.get_last_error()})")
    rc = _advapi32.SetNamedSecurityInfoW(
        path, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)
    if rc != 0:
        raise AclError(f"SetNamedSecurityInfoW failed ({rc})")
    if _owner_sid(path) != sid:        # the new ACL grants the user WRITE_OWNER, so this works
        rc = _advapi32.SetNamedSecurityInfoW(
            path, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION, sid_buf, None, None, None)
        if rc != 0:
            raise AclError(f"cannot make the current user the owner ({rc})")


def verify_current_user_only(path: str) -> None:
    """Read back the owner and DACL; raise AclError unless the user owns *path* and the
    DACL is protected and grants only the user."""
    _require_windows()
    sid = current_user_sid()
    sid_buf = ctypes.create_string_buffer(sid, len(sid))
    if _owner_sid(path) != sid:
        raise AclError("the directory is owned by another account")
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    rc = _advapi32.GetNamedSecurityInfoW(
        path, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, None, None,
        ctypes.byref(dacl), None, ctypes.byref(descriptor))
    if rc != 0:
        raise AclError(f"GetNamedSecurityInfoW failed ({rc})")
    try:
        control, revision = wt.WORD(0), wt.DWORD(0)
        if not _advapi32.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise AclError(f"GetSecurityDescriptorControl failed ({ctypes.get_last_error()})")
        if not control.value & SE_DACL_PROTECTED:
            raise AclError("DACL still inherits entries from the parent")
        if not dacl.value:
            raise AclError("directory has a NULL DACL (everyone has access)")
        info = _AclSizeInformation()
        if not _advapi32.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), ACL_SIZE_INFORMATION):
            raise AclError(f"GetAclInformation failed ({ctypes.get_last_error()})")
        if info.AceCount != 1:
            raise AclError(f"DACL has {info.AceCount} entries, expected 1")
        ace = ctypes.c_void_p()
        if not _advapi32.GetAce(dacl, 0, ctypes.byref(ace)):
            raise AclError(f"GetAce failed ({ctypes.get_last_error()})")
        # ACE_HEADER { BYTE AceType; BYTE AceFlags; WORD AceSize }, then DWORD Mask, then the SID.
        ace_type = ctypes.string_at(ace.value, 1)[0]
        mask = ctypes.c_uint32.from_address(ace.value + 4).value
        if ace_type != ACCESS_ALLOWED_ACE_TYPE:
            raise AclError("the only DACL entry is not an allow entry")
        if mask & FILE_ALL_ACCESS != FILE_ALL_ACCESS:
            raise AclError("the user does not have full control")
        if not _advapi32.EqualSid(ace.value + 8, sid_buf):
            raise AclError("the DACL entry is not for the current user")
    finally:
        if descriptor.value:
            _kernel32.LocalFree(descriptor)

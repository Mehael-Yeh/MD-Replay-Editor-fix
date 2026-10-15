"""Windows metadata change time (Python 3.11 st_ctime is creation time)."""
from functools import lru_cache


@lru_cache(maxsize=1)
def _windows_api():
    import ctypes
    from ctypes import wintypes

    class FileBasicInfo(ctypes.Structure):
        _fields_ = [(name, ctypes.c_longlong) for name in (
            'CreationTime', 'LastAccessTime', 'LastWriteTime', 'ChangeTime'
        )] + [('FileAttributes', wintypes.DWORD)]

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                ctypes.c_void_p, wintypes.DWORD]
    api.GetFileInformationByHandleEx.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api, FileBasicInfo


def windows_change_time(path):
    import ctypes
    api, info_type = _windows_api()
    # FILE_READ_ATTRIBUTES, share read/write/delete, OPEN_EXISTING.
    handle = api.CreateFileW(str(path.absolute()), 0x80, 7, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        return -1
    try:
        info = info_type()
        if not api.GetFileInformationByHandleEx(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
            return -1
        return info.ChangeTime
    finally:
        api.CloseHandle(handle)

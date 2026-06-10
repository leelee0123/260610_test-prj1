"""ffmpeg / ffprobe 실행 파일 경로 해석.

shutil.which()로 먼저 찾고, 없으면 Windows 레지스트리에서
Machine + User PATH를 직접 읽어 재탐색한다.
서버가 어떤 방식으로 시작되든 ffmpeg 위치를 찾을 수 있다.
"""
import os
import shutil
from functools import lru_cache


def _which_full(name: str) -> str | None:
    """현재 os.environ PATH → 레지스트리 전체 PATH 순서로 탐색."""
    found = shutil.which(name)
    if found:
        return found

    try:
        import winreg
        paths: list[str] = []
        for hive, subkey in [
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ]:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "PATH")
                    paths.append(val)
            except FileNotFoundError:
                pass
        full_path = ";".join(paths)
        found = shutil.which(name, path=full_path)
        if found:
            return found
    except Exception:
        pass

    return None


@lru_cache(maxsize=None)
def _resolve(name: str) -> str:
    path = _which_full(name)
    if path:
        return path
    raise FileNotFoundError(
        f"'{name}'을 찾을 수 없습니다. ffmpeg를 설치하고 PATH에 등록해 주세요.\n"
        "설치: https://ffmpeg.org/download.html"
    )


def ffmpeg() -> str:
    return _resolve("ffmpeg")


def ffprobe() -> str:
    return _resolve("ffprobe")

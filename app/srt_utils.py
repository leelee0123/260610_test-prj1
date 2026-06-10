"""SRT 타임코드/포맷 유틸. 타임코드는 항상 원본 세그먼트에서 생성·보존된다."""


def sec_to_timecode(sec: float) -> str:
    ms = round(sec * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(text: str) -> list[dict]:
    entries = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        entries.append({"index": int(lines[0]), "timecode": lines[1], "text": "\n".join(lines[2:])})
    return entries


def entries_to_srt(entries: list[dict]) -> str:
    return "\n\n".join(f"{e['index']}\n{e['timecode']}\n{e['text']}" for e in entries) + "\n"


def segments_to_srt(segments: list[dict]) -> str:
    blocks = []
    for i, seg in enumerate(segments, 1):
        blocks.append(
            f"{i}\n{sec_to_timecode(seg['start'])} --> {sec_to_timecode(seg['end'])}\n{seg['text']}"
        )
    return "\n\n".join(blocks) + "\n"

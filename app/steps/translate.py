"""③ (온프레미스) NLLB-200-1.3B로 외국어 자막 → 한국어 번역 → corrected.srt

타임코드는 GPT 교정과 동일한 방식으로 보존된다:
텍스트만 번역하고, SRT는 원본 파싱 결과의 타임코드로 재조립.
원본이 이미 한국어(ko)이면 번역 없이 원문을 그대로 corrected.srt로 복사한다.
"""
import json
import threading
from pathlib import Path

from app.device import get_device
from app.srt_utils import entries_to_srt, parse_srt

# faster-whisper BCP-47 → NLLB FLORES-200
LANG_MAP = {
    "af": "afr_Latn", "ar": "arb_Arab", "az": "azj_Latn",
    "be": "bel_Cyrl", "bg": "bul_Cyrl", "bn": "ben_Beng",
    "ca": "cat_Latn", "cs": "ces_Latn", "cy": "cym_Latn",
    "da": "dan_Latn", "de": "deu_Latn", "el": "ell_Grek",
    "en": "eng_Latn", "es": "spa_Latn", "et": "est_Latn",
    "fa": "pes_Arab", "fi": "fin_Latn", "fr": "fra_Latn",
    "gl": "glg_Latn", "gu": "guj_Gujr", "he": "heb_Hebr",
    "hi": "hin_Deva", "hr": "hrv_Latn", "hu": "hun_Latn",
    "hy": "hye_Armn", "id": "ind_Latn", "is": "isl_Latn",
    "it": "ita_Latn", "ja": "jpn_Jpan", "ka": "kat_Geor",
    "kk": "kaz_Cyrl", "km": "khm_Khmr", "kn": "kan_Knda",
    "ko": "kor_Hang", "lo": "lao_Laoo", "lt": "lit_Latn",
    "lv": "lvs_Latn", "mk": "mkd_Cyrl", "ml": "mal_Mlym",
    "mn": "khk_Cyrl", "mr": "mar_Deva", "ms": "zsm_Latn",
    "my": "mya_Mymr", "nb": "nob_Latn", "nl": "nld_Latn",
    "pl": "pol_Latn", "pt": "por_Latn", "ro": "ron_Latn",
    "ru": "rus_Cyrl", "sk": "slk_Latn", "sl": "slv_Latn",
    "sq": "als_Latn", "sr": "srp_Cyrl", "sv": "swe_Latn",
    "sw": "swh_Latn", "ta": "tam_Taml", "te": "tel_Telu",
    "th": "tha_Thai", "tl": "tgl_Latn", "tr": "tur_Latn",
    "uk": "ukr_Cyrl", "ur": "urd_Arab", "uz": "uzn_Latn",
    "vi": "vie_Latn", "zh": "zho_Hans",
}
TARGET = "kor_Hang"
BATCH = 30

_tokenizer = None
_model = None
_lock = threading.Lock()


def _get_model():
    global _tokenizer, _model
    if _model is None:
        with _lock:
            if _model is None:
                device, _, _ = get_device()
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                name = "facebook/nllb-200-1.3B"
                _tokenizer = AutoTokenizer.from_pretrained(name)
                _model = AutoModelForSeq2SeqLM.from_pretrained(name).to(device)
    return _tokenizer, _model


def _translate_batch(texts: list[str], src_flores: str) -> list[str]:
    tokenizer, model = _get_model()
    device = next(model.parameters()).device

    tokenizer.src_lang = src_flores
    inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
    tgt_id = tokenizer.convert_tokens_to_ids(TARGET)
    outputs = model.generate(
        **inputs,
        forced_bos_token_id=tgt_id,
        max_length=512,
        num_beams=5,
        no_repeat_ngram_size=3,
    )
    return tokenizer.batch_decode(outputs, skip_special_tokens=True)


def translate(job_dir: Path, report=lambda *a: None):
    entries = parse_srt((job_dir / "original.srt").read_text(encoding="utf-8"))

    meta_path = job_dir / "transcription_meta.json"
    src_lang = "unknown"
    if meta_path.exists():
        src_lang = json.loads(meta_path.read_text(encoding="utf-8")).get("language", "unknown")

    _, label, _ = get_device()

    # 한국어는 번역 없이 원문 복사
    if src_lang == "ko":
        report("원본이 한국어 — 번역 없이 복사", [])
        (job_dir / "corrected.srt").write_text(
            (job_dir / "original.srt").read_text(encoding="utf-8"), encoding="utf-8"
        )
        return entries

    src_flores = LANG_MAP.get(src_lang)
    if not src_flores:
        report(f"지원하지 않는 언어({src_lang}) — 원문 복사", [])
        (job_dir / "corrected.srt").write_text(
            (job_dir / "original.srt").read_text(encoding="utf-8"), encoding="utf-8"
        )
        return entries

    report(f"NLLB 모델 로드 중 ({label})")
    preview = []
    translated_texts: dict[int, str] = {}
    batches = [entries[i:i + BATCH] for i in range(0, len(entries), BATCH)]

    for bi, batch in enumerate(batches):
        report(f"NLLB 번역 중 ({src_lang}→ko) — 배치 {bi + 1}/{len(batches)} ({label})", preview)
        texts = [e["text"] for e in batch]
        results = _translate_batch(texts, src_flores)
        for e, translated in zip(batch, results):
            translated_texts[e["index"]] = translated.strip()
            preview.append(f"{e['text'][:20]}  →  {translated.strip()[:20]}")
        report(f"NLLB 번역 중 ({src_lang}→ko) — 배치 {bi + 1}/{len(batches)} 완료 ({label})", preview)

    out = [
        {"index": e["index"], "timecode": e["timecode"],
         "text": translated_texts.get(e["index"], e["text"])}
        for e in entries
    ]
    (job_dir / "corrected.srt").write_text(entries_to_srt(out), encoding="utf-8")
    return out

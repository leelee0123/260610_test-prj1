"""GPU/CPU 디바이스 감지 유틸리티 — 온프레미스 모델 공통 사용."""


def get_device() -> tuple[str, str, str]:
    """(device, label, compute_type) 반환.

    device:       "cuda" | "cpu"
    label:        "GPU: NVIDIA GeForce RTX 4080" 형태 또는 "CPU"
    compute_type: "float16" (CUDA) | "int8" (CPU)
    """
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return "cuda", f"GPU: {name}", "float16"
    except Exception:
        pass
    return "cpu", "CPU", "int8"

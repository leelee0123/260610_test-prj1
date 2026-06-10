# 영상 자동 분석 파이프라인 — 단계별 계획

## 개요

영상 파일 1개를 업로드하면 자동으로 ①오디오 추출 → ②Whisper 자막 → ③GPT 자막 교정 → ④장면 감지 → ⑤장면별 GPT 분석 → ⑥메타데이터 통합을 수행하는 웹 페이지.

- **입력**: 영상 파일 1개
- **출력**: 원본 SRT, 교정 SRT, 장면 메타데이터 JSON
- **제약**: 자막 타임코드 수정 금지, API 키는 `.env`로 관리

## 기술 결정

| 항목 | 결정 |
|---|---|
| 웹 스택 | FastAPI + 단순 HTML/JS |
| 음성 인식 | OpenAI Whisper API (`whisper-1`) |
| 장면 분석 입력 | 키프레임 이미지 + 해당 구간 자막 (GPT 비전) |
| 부가 도구 | ffmpeg(오디오/프레임 추출), PySceneDetect(장면 감지), python-dotenv |

## 프로젝트 구조

```
260610_Project1/
├─ .env.example          # OPENAI_API_KEY= (실제 .env는 .gitignore)
├─ requirements.txt
├─ PLAN.md               # 이 계획 문서
├─ app/
│  ├─ main.py            # FastAPI: 업로드 / 작업 상태 / 결과 다운로드 엔드포인트
│  ├─ pipeline.py        # ①~⑥ 단계 오케스트레이션 (백그라운드 작업)
│  ├─ steps/
│  │  ├─ audio.py        # ① ffmpeg 오디오 추출
│  │  ├─ transcribe.py   # ② Whisper API → original.srt
│  │  ├─ correct.py      # ③ GPT 텍스트 교정 → corrected.srt
│  │  ├─ scenes.py       # ④ PySceneDetect + 키프레임 추출
│  │  ├─ analyze.py      # ⑤ 장면별 GPT 비전 분석
│  │  └─ merge.py        # ⑥ metadata.json 통합
│  └─ static/index.html  # 업로드 + 진행률 + 결과 다운로드 UI
└─ jobs/<job_id>/        # 업로드 파일·중간 산출물·최종 결과 작업 폴더
```

## 구현 단계

```
1. 골격 구축 → 검증: 서버 기동, 파일 업로드가 jobs/<id>/에 저장됨
   - requirements.txt, .env.example, FastAPI 앱, 업로드 페이지

2. ① 오디오 추출 → 검증: jobs/<id>/audio.mp3 생성 확인
   - ffmpeg로 16kHz 모노 오디오 추출
   - Whisper API 25MB 제한 대비: 초과 시 길이 기준 분할

3. ② Whisper 자막 → 검증: original.srt가 표준 SRT 형식으로 파싱됨
   - response_format=verbose_json으로 세그먼트 타임스탬프 수신
   - 세그먼트 → SRT 변환 (분할 업로드 시 오프셋 보정)

4. ③ GPT 자막 교정 → 검증: 교정 전후 타임코드 diff가 0건
   - 자막 텍스트만 번호와 함께 배치로 GPT에 전달, 교정된 텍스트만 수신
   - 타임코드는 GPT에 보내지 않고 코드가 원본에서 그대로 재조립
     → "타임코드 수정 금지"를 프롬프트가 아닌 구조적으로 보장
   - 줄 수 불일치 시 해당 배치는 원본 유지(폴백)

5. ④ 장면 감지 → 검증: 장면 수 == 키프레임 수
   - PySceneDetect ContentDetector로 장면 경계(start/end) 검출
   - 각 장면 중간 지점 프레임을 ffmpeg로 JPEG 추출

6. ⑤ 장면별 GPT 분석 → 검증: 모든 장면에 대해 스키마 유효한 JSON 수신
   - 입력: 키프레임 이미지(base64) + 해당 구간 교정 자막
   - 출력(structured output): 요약, 등장 요소, 분위기, 자막-화면 연관성

7. ⑥ 메타데이터 통합 → 검증: metadata.json 스키마 검증 통과
   - 장면 타임코드 + 분석 결과 + 구간 자막 + 영상 기본 정보(길이, 해상도) 통합

8. 웹 UI 완성 → 검증: 짧은 샘플 영상으로 E2E 1회 통과
   - 단계별 진행 상태 폴링 표시, 3개 결과 파일 다운로드 링크
```

## 제약 사항 처리

- **타임코드 수정 금지**: ③에서 GPT에는 텍스트만 전달하고, SRT 재조립 시 원본 파싱 결과의 타임코드를 그대로 사용. 완료 후 원본/교정본 타임코드 자동 비교 검증.
- **API 키**: `OPENAI_API_KEY`를 `.env`에 두고 python-dotenv로 로드. `.env`는 `.gitignore`에 추가, `.env.example`만 커밋.

## metadata.json 스키마 (초안)

```json
{
  "video": { "filename": "...", "duration_sec": 0, "resolution": "1920x1080" },
  "scenes": [
    {
      "index": 1,
      "start": "00:00:00,000",
      "end": "00:00:12,340",
      "keyframe": "scene_001.jpg",
      "subtitles": [ { "index": 1, "start": "...", "end": "...", "text": "..." } ],
      "analysis": { "summary": "...", "elements": ["..."], "mood": "..." }
    }
  ]
}
```

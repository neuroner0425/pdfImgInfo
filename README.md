# vimatrax(Visual Material Transcription)

PDF속 시각자료를 텍스트로 바꿔주는 서비스입니다. 업로드한 PDF를 페이지별 이미지(JPEG)로 변환하고 멀티모달 LMM 모델을 통해 원문 텍스트와 의미 있는 이미지 묘사를 Markdown 코드 블록으로 추출합니다.

##  주요 기능
- 배치 처리 기반 PDF → 텍스트/이미지 설명 변환
- 변환 결과 Markdown 다운로드

## 환경 설정
### 1. 저장소 클론
```bash
git clone https://github.com/neuroner0425/vimatrax.git
cd imageIncludeFileTransFormer
```

### 2. 시스템 의존성 (Poppler - pdf2image 필요)
```bash
# macOS
brew install poppler

# Ubuntu/Debian:
sudo apt-get update && sudo apt-get install -y poppler-utils
```

### 3. 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. Gemini API Key 설정
```bash
export GEMINI_API_KEY="YOUR_API_KEY"          # 환경 변수로 설정
# 또는
echo "YOUR_API_KEY" > gemini_api_key.txt       # 루트 파일 생성
```

## 실행
```bash
# 명령어를 사용
uvicorn src.app:app --port 8000

# 쉘 스크립트를 사용
./start.sh
```

## 환경 변수
| 이름 | 기본값 | 설명 |
|------|--------|------|
| `GEMINI_API_KEY` | (없음) | Gemini API 키 (없으면 루트 `gemini_api_key.txt` 탐색) |
| `BATCH_SIZE` | 10 | 한 번의 Gemini 호출에 포함할 이미지 수 |
| `RETRY` | 2 | 배치 실패 시 재시도 횟수 |
| `DPI` | 200 | PDF 렌더링 해상도 |
| `WORKER_CONCURRENCY` | 4 | 동시에 실행할 워커 스레드 수 |
| `KEEP_IMAGES` | 0 | 1이면 변환된 이미지 파일 보존 |

##  디렉토리 구조
애플리케이션 소스는 `src/`, 실행 산출물과 템플릿/정적 파일은 프로젝트 루트에 위치합니다.
```
.
├─ pdf_jobs/                  # 작업별 워킹 디렉토리 (실행 중 생성)
├─ templates/                 # Jinja2 템플릿 (HTML UI)
├─ static/                    # 정적 파일 (CSS 등)
├─ gemini_api_key.txt         # (선택) Gemini API 키 파일
├─ src/
│  ├─ app.py                  # FastAPI 엔드포인트
│  ├─ config.py               # 환경 변수 & 경로 상수 & 기본 프롬프트
│  ├─ worker.py               # 워커/큐/실행 및 재큐잉 로직
│  ├─ job_persist.py          # 작업 메타 JSON 저장/로드
│  ├─ utils_text.py           # 문자열/정렬/코드펜스 유틸
│  └─ services/
│     ├─ pdf_service.py       # PDF → 이미지 변환 / 페이지 수 계산
│     └─ gemini_service.py    # Gemini 모델 초기화 & 배치 호출
├─ requirements.txt
└─ README.md
```

## 작업 처리 흐름
1. `POST /upload`: PDF 저장 → 작업 메타 등록 → 큐에 job_id push
2. 워커 스레드: PDF → 이미지(JPEG) 변환
3. 페이지 목록을 `BATCH_SIZE`로 분할, 각 배치 Gemini 호출
4. 배치별 Markdown 조각을 `---` 로 구분하여 병합
5. 결과 `result_<job_id>.md` 저장, 상태 DONE 전환

## 성능/튜닝
| 목표 | 조정 포인트 |
|------|-------------|
| 처리 속도 ↑ | `WORKER_CONCURRENCY` 증가 (API 한도 주의) |
| 비용 절감 | `BATCH_SIZE` 증가 (너무 크면 컨텍스트 한계 위험) |
| 품질 낮춰 속도 ↑ | `DPI` 낮추기 |
| 디스크 절약 | `KEEP_IMAGES=0` 유지 |
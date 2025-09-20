# PDF to Markdown Async Service

FastAPI 기반 비동기 PDF → Markdown 변환 서비스입니다. 업로드한 PDF를 페이지별 이미지(JPEG)로 변환 후, Gemini 모델을 통해 원문 텍스트와 의미 있는 이미지 묘사를 Markdown 코드 블록 형태로 추출합니다. 여러 페이지를 배치(Batch) 단위로 처리하며, 상태/결과를 조회하거나 최종 Markdown 파일을 다운로드할 수 있습니다.

## 주요 특징
- 비동기 처리: 업로드 직후 반환, 백그라운드 워커가 변환 진행
- 페이지 이미지 → Gemini API 배치 호출 → Markdown 병합
- 부분 실패 허용: 특정 배치 실패 시에도 전체 흐름 지속 (해당 배치 공백 메모)
- 서버 재기동 시 미완료 작업 자동 재큐잉
- 결과 Markdown 다운로드 제공

## 기술 스택
- **FastAPI**, **Uvicorn** (ASGI 서버)
- **pdf2image**, **Pillow** (PDF → Image 렌더링) ← Poppler 필요
- **google-generativeai** (Gemini 모델 호출)
- **Jinja2** (기본 HTML 템플릿)
- 표준 라이브러리: `threading`, `queue`, `tempfile`, `uuid`, `datetime` 등

## 디렉토리 구조 (요약)
리팩터링 후 모듈화된 구조:
```
.
├─ app.py                     # FastAPI 엔드포인트 (비즈니스 로직 위임)
├─ config.py                  # 환경 변수 & 경로 상수 & 기본 지시문
├─ worker.py                  # 워커/큐/실행 흐름 (run_job, requeue, shutdown)
├─ services/
│  ├─ pdf_service.py          # PDF → 이미지 렌더링 / 페이지 수 추정 / 이미지 로드
│  └─ gemini_service.py       # Gemini 모델 초기화 및 배치 호출 헬퍼
├─ utils_text.py              # 파일명 정규화, natural sort, 코드펜스 보장
├─ job_persist.py             # 작업 메타 JSON 저장/로드 (원자적 쓰기)
├─ templates/                 # Jinja2 템플릿 (상태/결과/업로드 UI)
├─ static/                    # 정적 파일 (CSS 등)
├─ pdf_jobs/                  # 작업별 워킹 디렉토리 (실행 중 생성)
├─ requirements.txt
└─ README.md
```

핵심 책임 분리:
## 디렉토리 구조 (요약 - 최신)
최근 경로 정책 변경: 실행 산출물 및 템플릿/정적 자산은 "루트" 경로, Python 애플리케이션 소스는 `src/` 하위에 위치합니다.
```
.
├─ pdf_jobs/                  # 작업별 워킹 디렉토리 (실행 중 동적 생성/사용)
├─ templates/                 # Jinja2 템플릿 (HTML UI)
├─ static/                    # 정적 파일 (CSS 등)
├─ gemini_api_key.txt         # (선택) API 키 파일
├─ src/
│  ├─ app.py                  # FastAPI 엔드포인트 (비즈니스 로직 위임)
│  ├─ config.py               # 환경 변수 & 경로 상수 & 기본 지시문 (루트 경로 기준)
│  ├─ worker.py               # 워커/큐/실행 흐름 (run_job, requeue, shutdown)
│  ├─ job_persist.py          # 작업 메타 JSON 저장/로드 (원자적 쓰기)
│  ├─ utils_text.py           # 파일명 정규화, natural sort, 코드펜스 보장
│  └─ services/
│     ├─ pdf_service.py       # PDF → 이미지 렌더링 / 페이지 수 추정 / 이미지 로드
│     └─ gemini_service.py    # Gemini 모델 초기화 및 배치 호출 헬퍼 (루트 키 파일 우선 탐색)
├─ requirements.txt
└─ README.md
```

핵심 책임 분리(불변):
- `src/app.py`: HTTP 계층 (입력 검증, JSON/HTML 응답, 작업 등록)
- `src/worker.py`: 작업 상태 전환/실행 + 재기동 복구
- `src/services/`: 도메인 기능 (PDF 처리, Gemini 호출)
- `src/utils_text.py`: 순수 유틸
- `src/config.py`: 경로/환경값 관리 (현재는 프로젝트 루트 기준으로 `pdf_jobs/`, `templates/`, `static/`를 바라봄)

## 설치 및 준비
### 1. 저장소 클론 & 진입
```bash
## 실행
경로 정책 변경(소스가 `src/` 하위)에 따라 아래 명령을 사용하세요.
```bash
# 가상환경 활성화 후 프로젝트 루트에서:
uvicorn src.app:app --reload --port 8000

# 또는 제공된 스크립트
./start.sh
```
git clone https://github.com/neuroner0425/pdfImgInfo.git
cd imageIncludeFileTransFormer

### 2. Python 환경 (권장)
```bash
## Gemini API Key 설정
아래 중 하나 선택 (우선순위: 환경변수 > 루트 `gemini_api_key.txt`):
```bash
export GEMINI_API_KEY="YOUR_API_KEY"
# 또는 프로젝트 루트에 gemini_api_key.txt 파일 생성 후 키 한 줄 기입
```
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
```

| `GEMINI_API_KEY` | (없음) | Gemini API 키 (없으면 루트 `gemini_api_key.txt` 탐색) |
macOS:
```bash
brew install poppler
```
Ubuntu/Debian:
```bash
sudo apt-get update && sudo apt-get install -y poppler-utils
```

### 4. 패키지 설치
```bash
pip install -r requirements.txt
```
- 환경변수:
  ```bash
  export GEMINI_API_KEY="YOUR_API_KEY"
  ```
- 또는 프로젝트 루트에 `gemini_api_key.txt` 생성 후 키 한 줄 저장

## 실행
```bash
브라우저에서:
## 한계 / 향후 개선 아이디어
- 배치별 부분 실패 재처리 API
- 페이지 단위 진행률
- 결과 Markdown 내 OCR/표 구조 재현
- 결과 및 작업 디렉토리 TTL/청소 스케줄러
- 구조화 로깅(JSON), OpenTelemetry 추적
- Prometheus 메트릭 (모델 호출 시간/에러 율)

## (마이그레이션 참고)
기존 버전에서 `src/templates/`, `src/static/`, `src/pdf_jobs/`를 사용하던 프로젝트라면 현재 실행 시 `src/config.py` 내 마이그레이션 로직이 루트 디렉토리로 자동 이동을 시도합니다. 충돌(동일 파일명) 발생 시 자동 덮어쓰지 않으므로, 필요 시 수동 정리:
```bash
mv src/templates/* templates/ 2>/dev/null || true
mv src/static/* static/ 2>/dev/null || true
mv src/pdf_jobs/* pdf_jobs/ 2>/dev/null || true
find src -type d -empty -maxdepth 1 -name 'templates' -delete 2>/dev/null || true
```
| 이름 | 기본값 | 설명 |
|------|--------|------|
| `GEMINI_API_KEY` | (없음) | Gemini API 키 또는 `gemini_api_key.txt` 사용 |
| `BATCH_SIZE` | 10 | 한 번의 Gemini 호출에 포함할 페이지 이미지 수 |
| `RETRY` | 2 | 배치 실패 시 재시도 횟수 |
| `DPI` | 200 | PDF 렌더링 해상도 (높을수록 선명/느림) |
| `WORKER_CONCURRENCY` | 4 | 동시 워커 스레드 수 |
| `KEEP_IMAGES` | 0 | 1 설정 시 변환된 페이지 이미지 보존 |

## 작업 흐름 상세
1. `POST /upload`
   - PDF 저장 (`pdf_jobs/<job_id>/input.pdf`)
   - 작업 메타 등록 후 즉시 job_id 반환 (또는 상태 페이지 리다이렉트)
2. 백그라운드 워커(`worker_loop`)
   - PDF → JPEG (페이지 순서 natural sort)
   - `BATCH_SIZE` 만큼 묶어 Gemini 호출 (`generate_content`)
   - Markdown 조각을 `---` 구분자로 결합, `result_<job_id>.md` 생성
3. 상태 조회 (`/job/{job_id}`)
   - JSON 또는 HTML (진행률 %, 완료 시 Markdown 미리보기)
4. 결과 다운로드 (`/download/{job_id}`)
5. 재기동: PENDING/RUNNING 상태 재큐잉 → 이어서 처리

## 오류 / 예외 처리
- PDF 렌더링 실패: 작업 상태 `실패`
- 배치 API 호출 실패: `RETRY` 내 재시도, 모두 실패 시 해당 배치 빈 코드블럭 기록
- 결과 파일 미존재 시 다운로드 요청 404

## 성능/튜닝 팁
| 상황 | 조정 권장 |
|------|-----------|
| 긴 PDF, 속도 중요 | `WORKER_CONCURRENCY` ↑ (과도 시 API 한도 유의) |
| 모델 호출 비용 절감 | `BATCH_SIZE` ↑ (너무 크면 context 길이 문제 가능) |
| 이미지 품질 저하 허용 | `DPI` ↓ |
| 디스크 사용 최소화 | `KEEP_IMAGES=0` 유지 |

## 보안 고려
- 업로드 파일은 즉시 고유 `job_id` 디렉토리에 저장
- 파일명은 내부적으로 고정(`input.pdf`), 다운로드 시 사용자 친화 이름 sanitize 적용
- 추가 인증/권한 통제 필요 시: 헤더 토큰 검증/미들웨어 구성을 별도 구현

## 한계 / 향후 개선 아이디어
- 배치별 부분 실패에 대한 재처리 재요청 API
- 진행률 보다 세밀한 (페이지 단위) 추적
- 결과 Markdown 내 이미지 OCR 추출/테이블 구조 재현
- 저장 정책(완료 후 N시간 보관) 자동 정리 스케줄러
 - 서비스/워커에 구조화 로깅(json) 적용 및 OpenTelemetry 추적
 - 모델 호출 시간/오류 통계 메트릭 (Prometheus) 노출


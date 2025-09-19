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
```
.
├─ app.py                # 메인 애플리케이션 (엔드포인트 + 워커 로직)
├─ job_persist.py        # 작업 메타 저장/로드 (JSON 직렬화) - 없을 경우 안전 실패
├─ templates/            # Jinja2 템플릿 (상태/결과/업로드 UI)
├─ static/               # 정적 파일 (CSS 등)
├─ pdf_jobs/             # 실행 중/완료된 작업 저장 디렉토리 (생성됨)
├─ requirements.txt
└─ README.md
```

## 설치 및 준비
### 1. 저장소 클론 & 진입
```bash
git clone https://github.com/neuroner0425/pdfImgInfo.git
cd imageIncludeFileTransFormer
```

### 2. Python 환경 (권장)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
```

### 3. 필수 시스템 의존 (Poppler)
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

### 5. Gemini API Key 설정
아래 중 하나 선택:
- 환경변수:
  ```bash
  export GEMINI_API_KEY="YOUR_API_KEY"
  ```
- 또는 프로젝트 루트에 `gemini_api_key.txt` 생성 후 키 한 줄 저장

## 실행
```bash
uvicorn app:app --reload --port 8000
```

브라우저에서:
- 업로드 UI: http://localhost:8000/upload
- 작업 상태: http://localhost:8000/job/<job_id>
- 전체 목록: http://localhost:8000/jobs
- 결과 다운로드: http://localhost:8000/download/<job_id>

## 환경 변수
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


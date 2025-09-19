"""main_web.py

FastAPI 기반 PDF -> Markdown 변환 비동기 서비스.

기능 요약:
1. PDF 업로드 -> 작업 등록 (비동기 처리)
2. PDF 각 페이지 이미지를 Gemini 배치 호출하여 Markdown 생성
3. 작업 상태 조회 (대기/처리중/완료/실패)
4. 결과 Markdown 다운로드

환경 변수 / 설정:
- GEMINI_API_KEY : Gemini API 키 (또는 gemini_api_key.txt 파일 사용)
- BATCH_SIZE (기본 10)
- RETRY (기본 2) : 배치 실패 재시도 횟수
- DPI (기본 200)
- KEEP_IMAGES ("1" 이면 변환된 이미지를 temp 디렉토리 유지)

실행:
    uvicorn main_web:app --reload --port 8010

의존성:
    pip install fastapi uvicorn pdf2image pillow google-generativeai
    (macOS) brew install poppler

엔드포인트:
    POST   /upload        -> multipart/form-data 로 pdf 업로드 (필드명: file)
    GET    /job/{job_id}  -> JSON/HTML 상태 조회
    GET    /download/{job_id} -> 결과 Markdown 다운로드

동시 처리(작업 소비) 모델:
        - 내부 큐(task_queue)에 업로드 시 job_id를 넣고, WORKER_CONCURRENCY 개수(기본 4)의
            worker_loop 스레드가 병렬로 소비하여 run_job 수행.
        - 환경변수 WORKER_CONCURRENCY 로 조정 (예: export WORKER_CONCURRENCY=2)
        - 종료 시 각 워커마다 sentinel(None)을 큐에 주입하여 안전하게 중단.

"""
from __future__ import annotations
import os
import re
import sys
import uuid
import shutil
import queue
import threading
import tempfile
from datetime import datetime
from typing import List, Optional, Dict, Any

# 작업 지속성 모듈
try:
    from job_persist import load_jobs as _load_jobs_json, save_jobs as _save_jobs_json
except Exception:
    _load_jobs_json = lambda: {}
    _save_jobs_json = lambda jobs: None

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# 외부 라이브러리 체크
try:
    from pdf2image import convert_from_path
except ImportError:
    print("[ERROR] pdf2image 미설치. pip install pdf2image pillow google-generativeai")
    sys.exit(1)
try:
    from PIL import Image
except ImportError:
    print("[ERROR] Pillow 미설치. pip install pillow")
    sys.exit(1)
try:
    import google.generativeai as genai
except ImportError:
    print("[ERROR] google-generativeai 미설치. pip install google-generativeai")
    sys.exit(1)

# ---------------- 설정 ----------------
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "10"))
RETRY = int(os.environ.get("RETRY", "2"))
DPI = int(os.environ.get("DPI", "200"))
KEEP_IMAGES = os.environ.get("KEEP_IMAGES", "0") == "1"
# 동시에 실행할 워커(작업 소비) 스레드 수. 기본 4.
# 환경변수 WORKER_CONCURRENCY 로 조정 가능.
WORKER_CONCURRENCY = int(os.environ.get("WORKER_CONCURRENCY", "4"))
MODEL_NAME_CANDIDATES = ["gemini-2.5-flash"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "pdf_jobs")
os.makedirs(STORAGE_DIR, exist_ok=True)

BASE_INSTRUCTIONS = (
    "보낸 이미지들은 강의 자료들인데, 시각 자료가 포함되어 있어. 용어 정리 부터 하면 '파일'은 내가 보낸 이미지 파일이고, '이미지'는 파일 안에 있는 시각 자료 이미지야.\n"
    "각 파일에 포함된 모든 내용을 마크다운 `코드`로 보내줘. 텍스트가 있다면 텍스트 원문 그대로를, 이미지가 있다면 이미지에 대한 설명을 적어줘. 파일 이름은 적지 않아도 돼. 모든 답을 하나의 마크다운 코드로 적어주고, 답변 이외의 아무 말도 하지 마.\n\n"
    "텍스트는 파일에 있는 `원문 그대로를 모두` 적어줘야해. 임의로 줄이거나 요약하지 마. 제목 소제목 등이 있다면 h3부터 시작해서 차례로 적어줘. 그리고 목록이 있다면 '- '기호를 사용해서 나열해서 적어줘. 예시는 다음과 같아\n\n"
    "```\n### 03. 네트워크 접속장치(LAN 카드)\n\n#### 1. LAN 카드\n\n- LAN 카드(NIC, Network Interface Card)는 두 대 이상의 컴퓨터로 네트워크를 구성하려고 외부 네트워크와 빠른 속도로 데이터를 송수신할 수 있게 컴퓨터 내에 설치하는 확장 카드를 말한다.\n- 네트워크에 연결하는 물리적 장치에는 반드시 하나의 LAN 카드가 있어야 한다. LAN 카드는 전송매체에 접속하는 역할과 데이터의 입출력 및 송수신, 프로토콜의 처리 기능 등을 담당한다.\n- 이 카드는 마더보드의 확장 슬롯에 설치하며, 네트워크 케이블을 연결하는 외부 포트를 포함하고 있다.\n\n> **NOTE 확장 슬롯(extended slot)**\n> 컴퓨터 본체 내부에 있는 소켓이다. 메모리, 하드디스크 인터페이스 보드, 그래픽 보드, 사운드 보드, LAN 보드 등의 확장 보드를 데이터 통로로 접속할 수 있도록 설계되어 있다.\n```\n\n"
    "불필요한 이미지에 대한 설명은 생략해도 돼. 하지만 이미지가 조금이라도 의미있다면 이미지에 대한 설명은 꼭 자세하게 작성해줘. 예시는 다음과 같아.\n\n"
    '"[이미지 설명: 다양한 네트워크 접속 장치를 사용한 네트워크 구성도. 라우터 아래에 스위치 A와 B가 있고, 각 스위치 아래에 허브 1과 2가 연결되어 있다. 허브들은 각각 여러 컴퓨터에 연결되며, 브리지를 통해 두 네트워크 간의 무선 연결도 이루어진다.]"\n\n'
    "만약 이미지에 대한 식별이 있다면 이미지 다음에 적어줘.\n"
    '"[그림 2-9 접속 장치로 연결된 네트워크]"\n\n'
    "그리고 각 파일들을 분리해서 답해주고, 파일들은 두 줄 건너뜀과 \"---\"으로 구분해줘. 파일 이름 오름차순으로 정렬해서 보내줘.\n\n"
    "마크다운 코드, 꼭 코드로 보내줘."
)

# ---------------- 상태 모델 ----------------
class JobStatus:
    PENDING = "대기"
    RUNNING = "처리중"
    DONE = "완료"
    FAILED = "실패"

jobs_lock = threading.Lock()
# 서버 재기동 시 기존 jobs.json 로드 (없으면 빈 dict)
jobs: Dict[str, Dict[str, Any]] = _load_jobs_json() or {}

# ---------------- Gemini 초기화 ----------------
_model_cached = None


def load_api_key() -> Optional[str]:
    # 우선 환경변수
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
    if k:
        return k.strip()
    # 파일 탐색
    key_file = os.path.join(BASE_DIR, "gemini_api_key.txt")
    if os.path.exists(key_file):
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    return None


def init_model():
    global _model_cached
    if _model_cached is not None:
        return _model_cached
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError("Gemini API 키를 찾을 수 없습니다 (환경변수 GEMINI_API_KEY 또는 gemini_api_key.txt)")
    genai.configure(api_key=api_key)
    last_error = None
    for name in MODEL_NAME_CANDIDATES:
        try:
            m = genai.GenerativeModel(name)
            _ = m.generate_content(["ping test"], safety_settings={})
            _model_cached = m
            print(f"[INFO] 모델 사용: {name}")
            return _model_cached
        except Exception as e:
            print(f"[WARN] 모델 초기화 실패 {name}: {e}")
            last_error = e
            continue
    raise RuntimeError(f"모든 모델 초기화 실패: {last_error}")

# ---------------- 유틸 ----------------

def natural_sort_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def pdf_to_images(pdf_path: str, output_dir: str, dpi: int) -> List[str]:
    from pdf2image import convert_from_path  # 지역 임포트 ( 워커 재사용 )
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
    except Exception as e:
        raise RuntimeError(f"PDF 렌더링 실패: {e}")
    if not images:
        raise RuntimeError("PDF에서 페이지를 렌더링하지 못했습니다.")
    os.makedirs(output_dir, exist_ok=True)
    out_list: List[str] = []
    for i, img in enumerate(images):
        out_path = os.path.join(output_dir, f"page_{i+1}.jpeg")
        try:
            img.save(out_path, 'JPEG')
            out_list.append(out_path)
        except Exception as e:
            print(f"[WARN] 페이지 저장 실패 {i+1}: {e}")
    return out_list

def load_images(paths: List[str]):
    loaded = []
    for p in paths:
        try:
            im = Image.open(p)
            loaded.append(im)
        except Exception as e:
            print(f"[WARN] 이미지 로드 실패 {p}: {e}")
    return loaded

def build_batch_prompt(batch_file_names: List[str]) -> str:
    header = "이 배치에 포함된 이미지 파일 이름 (참고용):\n" + "\n".join(f"- {os.path.basename(f)}" for f in batch_file_names) + "\n\n"
    return header + BASE_INSTRUCTIONS

def generate_for_batch(model, batch_paths: List[str]):
    file_names_sorted = sorted(batch_paths, key=natural_sort_key)
    prompt = build_batch_prompt(file_names_sorted)
    images = load_images(file_names_sorted)
    if not images:
        print("[WARN] 배치 이미지 로드 실패")
        return None
    
    parts = [prompt] + images
    try:
        resp = model.generate_content(parts, safety_settings={})
        resp.resolve()
        txt = resp.text or ""
        return txt.strip()
    except Exception as e:
        print(f"[ERROR] API 호출 실패 (배치 시작: {os.path.basename(file_names_sorted[0])}): {e}")
        return None

    # (전역 sanitize_filename 사용)
# ---------------- 파일명 처리 & PDF 메타 유틸 ----------------
def sanitize_filename(name: str) -> str:
    """업로드된 파일명(표시용) 정규화.
    - Unicode NFC 정규화
    - 허용 문자: 한글, 영문, 숫자, 공백, - _ . ( ) [ ] & , +
    - 연속 공백/구분자 정리 -> 단일 '_' 로 환산
    - 확장자 .pdf 제거 (있으면)
    - 앞뒤 trim 후 빈 문자열이면 'document'
    - 80자 제한
    """
    import unicodedata, re as _re
    name = unicodedata.normalize('NFC', name or '').strip().replace('\r', ' ').replace('\n', ' ')
    if name.lower().endswith('.pdf'):
        name = name[:-4]
    # 허용 외 문자 제거
    name = _re.sub(r'[^0-9A-Za-z가-힣 \-_\.\(\)\[\]&,+]', '', name)
    # 공백/구분자 연속 축소 -> '_'
    name = _re.sub(r'[\s]+', ' ', name).strip()
    name = name.replace(' ', '_')
    # 중복 '_' 축소
    name = _re.sub(r'[_]{2,}', '_', name)
    if not name:
        name = 'document'
    return name[:80]

def quick_pdf_page_count(pdf_path: str) -> int:
    """pdf 전체 페이지 이미지를 다 렌더링하지 않고 page count 를 얻기 위한 경량 시도.
    pdf2image 는 직접 메타만 얻는 기능이 없어 첫 렌더 시 전체 페이지를 생성하므로
    여기서는 convert_from_path 를 dpi=10, first_page/last_page trick 없이 호출 후 len 이용.
    (큰 파일에서도 상대적으로 빠른 편이지만 비용이 큰 경우 추후 PyPDF2 등으로 교체 가능)
    """
    try:
        from pdf2image import convert_from_path as _cfp
        imgs = _cfp(pdf_path, dpi=10)
        return len(imgs)
    except Exception:
        return 0

# ---------------- 워커 ----------------

task_queue: "queue.Queue[str]" = queue.Queue()


def worker_loop():
    while True:
        job_id = task_queue.get()
        if job_id is None:  # 종료 신호
            task_queue.task_done()
            break
        with jobs_lock:
            job = jobs.get(job_id)
            if not job:
                task_queue.task_done()
                continue
            job['status'] = JobStatus.RUNNING
            _save_jobs_json(jobs)
        try:
            run_job(job_id)
        except Exception as e:
            with jobs_lock:
                job = jobs.get(job_id)
                if job:
                    job['status'] = JobStatus.FAILED
                    job['error'] = str(e)
                    _save_jobs_json(jobs)
        finally:
            task_queue.task_done()


def run_job(job_id: str):
    with jobs_lock:
        job = jobs[job_id]
        pdf_path: str = job['pdf_path']
        batch_size: int = job['batch_size']
        retry: int = job['retry']
    # 준비
    model = init_model()
    # 이미지 디렉토리
    if KEEP_IMAGES:
        img_dir = os.path.join(job['work_dir'], 'images')
        os.makedirs(img_dir, exist_ok=True)
        temp_dir_created = False
    else:
        img_dir = tempfile.mkdtemp(prefix='pdfimgs_', dir=job['work_dir'])
        temp_dir_created = True

    image_paths = pdf_to_images(pdf_path, img_dir, dpi=DPI)
    image_paths.sort(key=lambda p: natural_sort_key(os.path.basename(p)))

    results = []
    for i in range(0, len(image_paths), batch_size):
        batch = image_paths[i:i+batch_size]
        attempt = 0
        batch_text = None
        while attempt <= retry:
            batch_text = generate_for_batch(model, batch)
            if batch_text:
                break
            attempt += 1
            if attempt <= retry:
                print(f"[INFO] 배치 재시도 {attempt}/{retry}")
        if batch_text:
            # 코드 펜스 보장
            cleaned = batch_text.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.strip('`')
                results.append(cleaned)
        else:
            results.append("```\n(이 배치에서 결과를 생성하지 못했습니다.)\n```")
        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                job['batches_done'] = job.get('batches_done', 0) + 1
                job['batches_total'] = (len(image_paths) + batch_size - 1)//batch_size
                _save_jobs_json(jobs)

    final_output = "\n\n---\n\n".join(results) + "\n"
    out_name = f"result_{job_id}.md"
    out_path = os.path.join(job['work_dir'], out_name)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(final_output)

    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job['status'] = JobStatus.DONE
            job['result_md'] = out_path
            job['completed_at'] = datetime.now().isoformat(timespec='seconds')
            _save_jobs_json(jobs)

    if temp_dir_created and not KEEP_IMAGES:
        try:
            shutil.rmtree(img_dir)
        except Exception as e:
            print(f"[WARN] 임시 이미지 삭제 실패: {e}")

# 워커 스레드들 시작 (동시 처리)
worker_threads: list[threading.Thread] = []
for _i in range(WORKER_CONCURRENCY):
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    worker_threads.append(t)

# ---------------- FastAPI 앱 ----------------
app = FastAPI(title="PDF to Markdown Service")
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
os.makedirs(TEMPLATE_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATE_DIR)
# Jinja 템플릿에서 datetime 사용 가능하도록 글로벌 등록
templates.env.globals['datetime'] = datetime
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

# ---------------- 엔드포인트 ----------------

@app.post('/upload')
async def upload_pdf(request: Request, file: UploadFile = File(...), batch_size: Optional[int] = None, retry: Optional[int] = None, filename: Optional[str] = None):
    if file.content_type not in ('application/pdf', 'application/octet-stream') and not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail='PDF 파일이 아닙니다.')
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail='빈 파일입니다.')
    job_id = str(uuid.uuid4())
    work_dir = os.path.join(STORAGE_DIR, job_id)
    os.makedirs(work_dir, exist_ok=True)
    pdf_path = os.path.join(work_dir, 'input.pdf')
    with open(pdf_path, 'wb') as f:
        f.write(data)
    bsize = batch_size if batch_size and batch_size > 0 else BATCH_SIZE
    rtry = retry if retry is not None and retry >= 0 else RETRY
    original_name = file.filename or 'uploaded.pdf'
    user_base = filename if filename else original_name
    safe_name = sanitize_filename(user_base)
    # 페이지 수 / 예상 배치 수 선계산
    page_count = quick_pdf_page_count(pdf_path)
    pre_batches_total = (page_count + bsize - 1)//bsize if page_count else None
    with jobs_lock:
        jobs[job_id] = {
            'status': JobStatus.PENDING,
            'pdf_path': pdf_path,
            'job_id': job_id,
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'batch_size': bsize,
            'retry': rtry,
            'work_dir': work_dir,
            'batches_done': 0,
            'batches_total': pre_batches_total,
            'page_count': page_count,
            'file_name': safe_name,           # 사용자(또는 기본) 지정 이름 (확장자 제외)
            'original_file_name': original_name,
        }
        _save_jobs_json(jobs)
    task_queue.put(job_id)
    # 요청이 JSON 기반인지(form vs fetch) 판별: 헤더 Accept/ X-Requested-With 참고
    accept = request.headers.get('accept','')
    if 'application/json' in accept:
        return { 'job_id': job_id }
    # 브라우저 폼 업로드라면 상태 페이지로 리다이렉트
    return RedirectResponse(url=f'/job/{job_id}', status_code=303)

@app.get('/upload')
async def pdf_ui(request: Request):
    return templates.TemplateResponse('upload.html', { 'request': request })

@app.get('/view/{job_id}')
async def pdf_view(request: Request, job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='작업을 찾을 수 없습니다.')
    return templates.TemplateResponse('result_view.html', { 'request': request, 'job': job })

@app.get('/')
async def root_home(request: Request):
    # 홈 화면 (업로드와 분리)
    return templates.TemplateResponse('home.html', { 'request': request })

@app.get('/job/{job_id}', response_class=HTMLResponse)
async def job_page(request: Request, job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='작업을 찾을 수 없습니다.')
    # 진행률 계산
    progress = None
    if job.get('batches_total'):
        try:
            progress = int(job.get('batches_done', 0) / job['batches_total'] * 100)
        except Exception:
            progress = None
    job['progress_percent'] = progress
    # HTML vs JSON 결정
    accept = request.headers.get('accept','')
    if 'application/json' in accept:
        resp = {k: v for k, v in job.items() if k not in ('pdf_path','work_dir')}
        return JSONResponse(resp)
    # 상태별 템플릿
    if job['status'] in (JobStatus.PENDING, JobStatus.RUNNING):
        return templates.TemplateResponse('waiting.html', { 'request': request, 'job': job })
    elif job['status'] == JobStatus.DONE:
        # Markdown 내용 로드
        md_text = ''
        result_path = job.get('result_md')
        if result_path and os.path.exists(result_path):
            try:
                with open(result_path, 'r', encoding='utf-8') as rf:
                    md_text = rf.read()
            except Exception as e:
                md_text = f"(결과 파일 읽기 실패: {e})"
        return templates.TemplateResponse('result_view.html', { 'request': request, 'job': job, 'markdown_text': md_text })
    else:  # FAILED
        return templates.TemplateResponse('result_view.html', { 'request': request, 'job': job, 'markdown_text': '' })

@app.get('/jobs', response_class=HTMLResponse)
async def jobs_list(request: Request):
    with jobs_lock:
        items = list(jobs.items())[::-1]
    accept = request.headers.get('accept','')
    if 'application/json' in accept:
        serial = []
        for jid, j in items:
            copy = {k:v for k,v in j.items() if k not in ('pdf_path','work_dir')}
            copy['job_id'] = jid
            serial.append(copy)
        return JSONResponse({'jobs': serial})
    return templates.TemplateResponse('jobs.html', { 'request': request, 'job_items': items })

@app.get('/download/{job_id}')
async def download_result(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail='작업을 찾을 수 없습니다.')
        if job['status'] != JobStatus.DONE:
            raise HTTPException(status_code=400, detail='작업이 아직 완료되지 않았습니다.')
        result_path = job.get('result_md')
        if not result_path or not os.path.exists(result_path):
            raise HTTPException(status_code=404, detail='결과 파일을 찾을 수 없습니다.')
    base_name = job.get('file_name') or job_id
    filename = f"{base_name}.md"
    return FileResponse(result_path, media_type='text/markdown', filename=filename)

@app.get('/healthz')
async def healthz():
    return {"status": "ok"}

# ---------------- 종료 훅 ----------------
@app.on_event("startup")
async def startup_event():
    # 재기동 시 미완료 작업 복구
    requeue_count = 0
    with jobs_lock:
        for jid, j in jobs.items():
            if j.get('status') in (JobStatus.PENDING, JobStatus.RUNNING):
                # RUNNING 중이던 것도 다시 대기로 전환
                j['status'] = JobStatus.PENDING
                # 진행률 유지 (부분 완료된 배치 수) -> 계속 진행
                task_queue.put(jid)
                requeue_count += 1
        if requeue_count:
            _save_jobs_json(jobs)
    if requeue_count:
        print(f"[INFO] 재기동 복구: {requeue_count}개 작업 재큐잉")

@app.on_event("shutdown")
async def shutdown_event():
    # 각 워커 스레드당 하나씩 sentinel(None) 투입
    for _ in worker_threads:
        try:
            task_queue.put_nowait(None)
        except Exception:
            pass
    # 조인
    for t in worker_threads:
        try:
            t.join(timeout=5)
        except Exception:
            pass

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8010, reload=True)

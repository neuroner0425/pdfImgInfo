"""PDF -> Markdown 비동기 변환 서비스 (FastAPI)

리팩터링: 대형 단일 파일을 config / services / worker / utils 로 분리.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime
from typing import Optional
import math
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from .config import BATCH_SIZE, RETRY, STORAGE_DIR, TEMPLATE_DIR, STATIC_DIR
import markdown as md
from .worker import jobs, jobs_lock, task_queue, JobStatus, requeue_pending, shutdown_workers
from .services.pdf_service import quick_pdf_page_count
from .utils_text import sanitize_filename
from .job_persist import save_jobs as _save_jobs_json

@asynccontextmanager
async def lifespan(app: FastAPI):
    requeue_pending()
    yield
    shutdown_workers()

app = FastAPI(title="vimatrax", lifespan=lifespan)
templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals['datetime'] = datetime
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

class UvicornAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # return True to keep, False to drop
        try:
            msg = record.getMessage()
            # uvicorn access log lines typically contain the HTTP method and path like: '"GET /job/<id> '
            if 'GET /job/' in msg or 'POST /job/' in msg:
                return False
        except Exception:
            # on any unexpected issue, don't block the log
            return True
        return True

# Attach filter to uvicorn access logger if present
try:
    _access_logger = logging.getLogger('uvicorn.access')
    _access_logger.addFilter(UvicornAccessFilter())
except Exception:
    pass

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
    rtry = retry if retry is not None and retry >= 0 else RETRY
    original_name = file.filename or 'uploaded.pdf'
    user_base = filename if filename else original_name
    safe_name = sanitize_filename(user_base)
    # 페이지 수 / 예상 배치 수 선계산
    page_count = quick_pdf_page_count(pdf_path)
    dynamic_batch_size = math.ceil(page_count / (math.ceil(page_count / BATCH_SIZE))) if page_count and page_count > 0 else BATCH_SIZE
    bsize = batch_size if batch_size and batch_size > 0 else dynamic_batch_size
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
            'file_name': safe_name,
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
        html_converted = ''
        result_path = job.get('result_md')
        if result_path and os.path.exists(result_path):
            try:
                with open(result_path, 'r', encoding='utf-8') as rf:
                    md_text = rf.read()
                # Markdown -> HTML 변환 (테이블/코드블럭/목차 확장)
                html_converted = md.markdown(
                    md_text,
                    extensions=[
                        'extra',          # tables, fenced code 등
                        'admonition',     # 추가 블록
                        'codehilite',     # 코드 하이라이트 (추가 CSS 필요 가능)
                        'tables',
                        'fenced_code'
                    ]
                )
            except Exception as e:
                md_text = f"(결과 파일 읽기 실패: {e})"
                html_converted = ''
        return templates.TemplateResponse('result_view.html', { 'request': request, 'job': job, 'markdown_text': md_text, 'markdown_html': html_converted })
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



if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

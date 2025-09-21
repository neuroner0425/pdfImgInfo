"""작업 큐/워커 및 실행 로직.

FastAPI 엔드포인트는 이 모듈의 jobs / enqueue / 상태 조회 기능을 사용한다.
"""
from __future__ import annotations
import os
import shutil
import tempfile
import threading
import queue
from datetime import datetime
from typing import Dict, Any, List

from .config import DPI, KEEP_IMAGES, BATCH_SIZE, RETRY, STORAGE_DIR, WORKER_CONCURRENCY
from .job_persist import load_jobs as _load_jobs_json, save_jobs as _save_jobs_json, batch_log
from .services.pdf_service import pdf_to_images, extract_text_by_page
from .services.gemini_service import init_model, generate_for_batch
from .utils_text import natural_sort_key, ensure_code_fence

class JobStatus:
    PENDING = "대기"
    RUNNING = "처리중"
    DONE = "완료"
    FAILED = "실패"

jobs_lock = threading.Lock()
jobs: Dict[str, Dict[str, Any]] = _load_jobs_json() or {}

task_queue: "queue.Queue[str]" = queue.Queue()
worker_threads: List[threading.Thread] = []

def run_job(job_id: str):
    model = init_model()
    started = datetime.now()
    with jobs_lock:
        job = jobs[job_id]
        pdf_path: str = job['pdf_path']
        batch_size: int = job['batch_size']
        retry: int = job['retry']
        jobs[job_id]['started_at'] = started.strftime('%Y-%m-%d %H:%M:%S')
        jobs[job_id]['started_ts'] = started.timestamp()
    if KEEP_IMAGES:
        img_dir = os.path.join(job['work_dir'], 'images')
        os.makedirs(img_dir, exist_ok=True)
        temp_dir_created = False
    else:
        img_dir = tempfile.mkdtemp(prefix='pdfimgs_', dir=job['work_dir'])
        temp_dir_created = True
    image_paths = pdf_to_images(pdf_path, img_dir, dpi=DPI)
    image_paths.sort(key=lambda p: natural_sort_key(os.path.basename(p)))
    
    pdf_texts = extract_text_by_page(pdf_path)
    results = []
    for i in range(0, len(image_paths), batch_size):
        batch_start = datetime.now()
        batch_img = image_paths[i:i+batch_size]
        batch_pdf_texts = pdf_texts[i:i+batch_size]
        prompt = "다음은 PyMuPDF로 추출한 슬라이드별 텍스트입니다.\n\n" + "".join(f"--- 페이지 {i+j+1} --- \n{txt}\n\n" for j, txt in enumerate(batch_pdf_texts) if txt.strip())
        attempt = 0
        batch_text = None
        while attempt <= retry:
            batch_text = generate_for_batch(model, batch_img, prompt=prompt)
            if batch_text:
                break
            attempt += 1
            if attempt <= retry:
                print(f"[INFO] 배치 재시도 {attempt}/{retry}")
        if batch_text:
            results.append(ensure_code_fence(batch_text))
        else:
            results.append(ensure_code_fence("(이 배치에서 결과를 생성하지 못했습니다.)"))
        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                batch_end = datetime.now()
                batch_duration = (batch_end - batch_start).total_seconds()
                batch_log(batch_size, batch_duration)
                job['batches_done'] = job.get('batches_done', 0) + 1
                job['batches_total'] = (len(image_paths) + batch_size - 1)//batch_size
                _save_jobs_json(jobs)
    final_output = "\n\n---\n\n".join(results) + "\n"
    out_name = f"result_{job_id}.md"
    out_path = os.path.join(job['work_dir'], out_name)
    end_time = datetime.now()
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(final_output)
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job['status'] = JobStatus.DONE
            job['result_md'] = out_path
            job['completed_at'] = end_time.isoformat(timespec='seconds')
            job['completed_ts'] = end_time.timestamp()
            _save_jobs_json(jobs)
    if temp_dir_created and not KEEP_IMAGES:
        try:
            shutil.rmtree(img_dir)
        except Exception as e:
            print(f"[WARN] 임시 이미지 삭제 실패: {e}")

def worker_loop():
    while True:
        job_id = task_queue.get()
        if job_id is None:
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

def start_workers():
    if worker_threads:
        return
    for _ in range(WORKER_CONCURRENCY):
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        worker_threads.append(t)

def requeue_pending():
    requeue_count = 0
    with jobs_lock:
        for jid, j in jobs.items():
            if j.get('status') in (JobStatus.PENDING, JobStatus.RUNNING):
                j['status'] = JobStatus.PENDING
                task_queue.put(jid)
                requeue_count += 1
        if requeue_count:
            _save_jobs_json(jobs)
    if requeue_count:
        print(f"[INFO] 재기동 복구: {requeue_count}개 작업 재큐잉")
    return requeue_count

def shutdown_workers():
    for _ in worker_threads:
        task_queue.put(None)
    for t in worker_threads:
        try:
            t.join(timeout=5)
        except Exception:
            pass

# 모듈 import 시 워커 자동 시작 (앱 시작 이벤트 전에 안전하게 준비)
start_workers()

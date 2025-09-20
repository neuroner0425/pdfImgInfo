"""Gemini 모델 초기화 및 배치 생성 로직."""
from __future__ import annotations
import os
from typing import List, Optional

import google.generativeai as genai

from ..config import MODEL_NAME_CANDIDATES, BASE_INSTRUCTIONS, PROJECT_ROOT
from .pdf_service import load_images
from ..utils_text import natural_sort_key

_model_cached = None

def load_api_key() -> Optional[str]:
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
    if k:
        return k.strip()
    # 우선 순위: 루트 -> services 상위
    candidate_files = [
        os.path.join(PROJECT_ROOT, 'gemini_api_key.txt'),
        os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gemini_api_key.txt')),
    ]
    for key_file in candidate_files:
        if os.path.exists(key_file):
            try:
                with open(key_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return content
            except Exception:
                continue
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

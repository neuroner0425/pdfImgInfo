"""Gemini 모델 초기화 및 배치 생성 로직."""
from __future__ import annotations
import os
from typing import List, Optional

from google import genai, genai
from google.genai import types
from google.genai.types import GenerateContentConfig

from ..config import MODEL_NAME_CANDIDATES, BASE_INSTRUCTIONS, PROJECT_ROOT
from ..utils_text import natural_sort_key

_model_cached: genai.Client = None

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
    last_error = None
    for name in MODEL_NAME_CANDIDATES:
        try:
            m = genai.Client(api_key=api_key)
            # _ = m.generate_content(["ping test"], safety_settings={})
            _model_cached = m
            print(f"[INFO] 모델 사용: {name}")
            return _model_cached
        except Exception as e:
            print(f"[WARN] 모델 초기화 실패 {name}: {e}")
            last_error = e
            continue
    raise RuntimeError(f"모든 모델 초기화 실패: {last_error}")

def load_images(file_paths: List[str]) -> List[types.Part]:
    images = []
    for fp in file_paths:
        try:
            with open(fp, 'rb') as f:
                loaded_file_bytes = f.read()
            loaded_file = types.Part.from_bytes(data=loaded_file_bytes, mime_type="image/jpeg")
            images.append(loaded_file)
        except Exception as e:
            print(f"[WARN] 이미지 로드 실패 {fp}: {e}")
            continue
    return images

def generate_for_batch(model: genai.Client, batch_paths: List[str], prompt: str = ""):
    """
    주어진 이미지 파일 경로 리스트(batch_paths)에 대해 이미지를 로드하고,
    지정된 모델(model)을 사용하여 배치 프롬프트와 함께 Gemini API에 요청을 보낸 후 결과 텍스트를 반환합니다.

    Args:
        model: Gemini API를 호출할 모델 인스턴스.
        batch_paths (List[str]): 처리할 이미지 파일 경로들의 리스트.

    Returns:
        str | None: 모델의 응답 텍스트(성공 시), 실패 시 None.
    """
    file_names_sorted = sorted(batch_paths, key=natural_sort_key)
    images: list = load_images(file_names_sorted)
    if not images:
        print("[WARN] 배치 이미지 로드 실패")
        return None
    contents = []
    if prompt.strip():
        contents.append(prompt)
    contents.extend(images)
    try:
        resp = model.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=GenerateContentConfig(
                system_instruction=BASE_INSTRUCTIONS,
                temperature=0.9,
            ),
        )
        txt = resp.text.strip() or ""
        return txt
    except Exception as e:
            print(f"[ERROR] API 호출 실패 (배치 시작: {os.path.basename(file_names_sorted[0])}): {e}")
            return None

"""PDF 관련 처리 (렌더링, 페이지 수 추정, 이미지 로딩)."""
from __future__ import annotations
import os
from typing import List

from pdf2image import convert_from_path
from PIL import Image

def pdf_to_images(pdf_path: str, output_dir: str, dpi: int) -> List[str]:
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

def quick_pdf_page_count(pdf_path: str) -> int:
    try:
        imgs = convert_from_path(pdf_path, dpi=10)
        return len(imgs)
    except Exception:
        return 0

"""텍스트 및 파일명 처리 유틸리티 함수 모음."""
from __future__ import annotations
import re
import unicodedata
from typing import List, Any

def natural_sort_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

def sanitize_filename(name: str) -> str:
    """업로드된 파일명(표시용) 정규화.
    - Unicode NFC 정규화
    - 허용 문자: 한글, 영문, 숫자, 공백, - _ . ( ) [ ] & , +
    - 연속 공백 -> '_' 로 치환
    - 확장자 .pdf 제거
    - 80자 제한
    """
    name = unicodedata.normalize('NFC', name or '').strip().replace('\r', ' ').replace('\n', ' ')
    if name.lower().endswith('.pdf'):
        name = name[:-4]
    name = re.sub(r'[^0-9A-Za-z가-힣 \-_\.\(\)\[\]&,+]', '', name)
    name = re.sub(r'[\s]+', ' ', name).strip().replace(' ', '_')
    name = re.sub(r'[_]{2,}', '_', name)
    if not name:
        name = 'document'
    return name[:80]

def ensure_code_fence(text: str) -> str:
    t = (text or '').strip()
    if not t:
        return "```\n(빈 결과)\n```"
    if t.startswith('```'):
        t = t.strip('`').strip()
        return t
    return f"\n{t}\n"

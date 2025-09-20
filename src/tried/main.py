"""main.py

PDF를 페이지 단위 이미지(JPEG)로 변환한 뒤, 지정된 배치 크기만큼 Gemini 모델에 보내어
각 페이지 내용을 마크다운 코드블록 형태로 추출/설명하는 통합 스크립트.

주요 기능:
1. PDF -> JPEG 변환 (pdf2image)
2. 이미지 파일 배치 처리 (사용자 지정 batch size)
3. Gemini (google-generativeai) API 호출로 텍스트/이미지 설명 결과 수집
4. 모든 배치 결과를 구분선(---)으로 이어 붙여 Markdown 파일 저장
5. 실패한 배치는 재시도 옵션 제공
6. 임시 이미지 디렉토리 자동 정리 (원하면 유지 가능)

사용 예시:
    python main.py input.pdf -o output.md -b 8 --dpi 200 --retry 2 --keep-images

API 키 우선순위:
    1. -k / --api-key 인자
    2. 현재 디렉토리의 gemini_api_key.txt 파일
    3. 환경변수 GEMINI_API_KEY 또는 API_KEY
    4. 콘솔 입력

필요 패키지 설치:
    pip install pdf2image pillow google-generativeai

macOS에서 poppler 설치 (pdf2image 의존):
    brew install poppler

"""

import os
import re
import sys
import shutil
import argparse
import tempfile
from datetime import datetime
from typing import List

# 외부 라이브러리 준비 체크
try:
    from pdf2image import convert_from_path
except ImportError:
    print("[ERROR] pdf2image 패키지가 없습니다. 설치: pip install pdf2image pillow google-generativeai")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("[ERROR] Pillow 패키지가 없습니다. 설치: pip install pillow")
    sys.exit(1)

try:
    import google.generativeai as genai
except ImportError:
    print("[ERROR] google-generativeai 패키지가 없습니다. 설치: pip install google-generativeai")
    sys.exit(1)

# ------------------ 설정 상수 ------------------
DEFAULT_BATCH_SIZE = 10
DEFAULT_RETRY = 2  # 각 배치 실패 시 재시도 횟수
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")
MODEL_NAME_CANDIDATES = [
    "gemini-2.5-flash"
]
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

# ------------------ 유틸 함수 ------------------

def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]

def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 200) -> List[str]:
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
    except Exception as e:
        raise RuntimeError(f"PDF 렌더링 실패: {e}")
    if not images:
        raise RuntimeError("PDF에서 렌더링된 페이지가 없습니다.")
    os.makedirs(output_dir, exist_ok=True)
    saved_paths: List[str] = []
    for i, image in enumerate(images):
        out_path = os.path.join(output_dir, f"page_{i+1}.jpeg")
        try:
            image.save(out_path, 'JPEG')
        except Exception as e:
            print(f"[WARN] 페이지 {i+1} 저장 실패: {e}")
            continue
        saved_paths.append(out_path)
    return saved_paths

def load_images(paths: List[str]):
    loaded = []
    for p in paths:
        try:
            img = Image.open(p)
            loaded.append(img)
        except Exception as e:
            print(f"[WARN] 이미지 로드 실패 {p}: {e}")
    return loaded

def build_batch_prompt(batch_file_names: List[str]) -> str:
    header = "이 배치에 포함된 이미지 파일 이름 (참고용):\n" + "\n".join(f"- {os.path.basename(f)}" for f in batch_file_names) + "\n\n"
    return header + BASE_INSTRUCTIONS

# ------------------ Gemini 처리 ------------------

def init_model(api_key: str):
    genai.configure(api_key=api_key)
    last_error = None
    for name in MODEL_NAME_CANDIDATES:
        try:
            model = genai.GenerativeModel(name)
            _ = model.generate_content(["ping test"], safety_settings={})
            print(f"[INFO] 모델 사용: {name}")
            return model
        except Exception as e:
            last_error = e
            print(f"[WARN] 모델 초기화 실패 {name}: {e}")
            continue
    raise RuntimeError(f"모든 후보 모델 초기화 실패: {last_error}")

def generate_for_batch(model, batch_paths: List[str]):
    file_names_sorted = sorted(batch_paths, key=natural_sort_key)
    prompt = build_batch_prompt(file_names_sorted)
    images = load_images(file_names_sorted)
    if not images:
        print("[WARN] 배치 내 이미지 로드 실패 -> 스킵")
        return None
    parts = [prompt] + images
    try:
        response = model.generate_content(parts, safety_settings={})
        response.resolve()
        text = response.text or ""
        return text.strip()
    except Exception as e:
        print(f"[ERROR] API 호출 실패 (배치 시작: {os.path.basename(file_names_sorted[0])}): {e}")
        return None

# ------------------ 핵심 실행 로직 ------------------

def process_pdf(pdf_path: str, api_key: str, batch_size: int, output_md: str | None, keep_images: bool, dpi: int, retry: int):
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    model = init_model(api_key)

    # 임시 디렉토리 (또는 유지 옵션)
    temp_dir_created = False
    if keep_images:
        base_dir = os.path.join(os.getcwd(), f"temp_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(base_dir, exist_ok=True)
    else:
        base_dir = tempfile.mkdtemp(prefix="pdfimgs_")
        temp_dir_created = True

    print(f"[INFO] PDF -> 이미지 변환중 (dpi={dpi}) ...")
    image_paths = pdf_to_images(pdf_path, base_dir, dpi=dpi)
    if not image_paths:
        raise RuntimeError("이미지 변환 결과가 비어 있습니다.")

    image_paths.sort(key=lambda p: natural_sort_key(os.path.basename(p)))
    print(f"[INFO] 총 {len(image_paths)}개 페이지 이미지 생성. 배치 크기: {batch_size}")

    results = []
    for i in range(0, len(image_paths), batch_size):
        batch = image_paths[i:i + batch_size]
        print(f"[INFO] 배치 처리: {i + 1} ~ {i + len(batch)} (총 {len(batch)}개)")
        attempt = 0
        batch_text = None
        while attempt <= retry:
            batch_text = generate_for_batch(model, batch)
            if batch_text:
                break
            attempt += 1
            if attempt <= retry:
                print(f"[INFO] 재시도 {attempt}/{retry} ...")
        if batch_text:
            if batch_text.startswith("```") and batch_text.endswith("```"):
                # 이미 코드 블록이면 그대로 사용
                results.append(batch_text.strip())
            else:
                # 코드 블록으로 감싸기
                results.append(f"```\n{batch_text}\n```")
        else:
            results.append("```\n(이 배치에서 결과를 생성하지 못했습니다.)\n```")

    final_output = "\n\n---\n\n".join(results) + "\n"

    if not output_md:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_md = f"gemini_result_{ts}.md"
    out_path = os.path.abspath(output_md)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_output)
    print(f"[INFO] 결과 저장: {out_path}")

    if temp_dir_created and not keep_images:
        try:
            shutil.rmtree(base_dir)
            print(f"[INFO] 임시 이미지 디렉토리 삭제: {base_dir}")
        except Exception as e:
            print(f"[WARN] 임시 디렉토리 삭제 실패: {e}")
    else:
        print(f"[INFO] 이미지 디렉토리 유지: {base_dir}")

# ------------------ API 키 로딩 ------------------

def load_api_key(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    key_file = os.path.join(os.path.dirname(__file__), "gemini_api_key.txt")
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            content = f.read().strip()
            if content:
                return content
    # 환경변수
    env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
    if env_key:
        return env_key.strip()
    # 마지막으로 사용자 입력
    return input("Gemini API 키를 입력하세요: ").strip()

# ------------------ CLI ------------------

def build_arg_parser():
    p = argparse.ArgumentParser(description="PDF를 페이지 이미지로 변환 후 Gemini로 배치 처리하여 Markdown 추출")
    p.add_argument("pdf", help="입력 PDF 경로")
    p.add_argument("-o", "--output", help="결과 저장할 Markdown 파일 경로 (기본: gemini_result_타임스탬프.md)")
    p.add_argument("-k", "--api-key", help="직접 API 키 지정 (파일/환경변수/입력 순서)")
    p.add_argument("-b", "--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"배치 크기 (기본: {DEFAULT_BATCH_SIZE})")
    p.add_argument("--dpi", type=int, default=200, help="PDF 렌더링 DPI (기본: 200)")
    p.add_argument("-r", "--retry", type=int, default=DEFAULT_RETRY, help=f"배치 실패 시 재시도 횟수 (기본: {DEFAULT_RETRY})")
    p.add_argument("--keep-images", action="store_true", help="변환된 이미지 디렉토리를 삭제하지 않고 유지")
    return p

def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    api_key = load_api_key(args.api_key)
    if not api_key:
        print("[ERROR] API 키를 제공받지 못했습니다.")
        sys.exit(1)

    try:
        process_pdf(
            pdf_path=args.pdf,
            api_key=api_key,
            batch_size=max(1, args.batch_size),
            output_md=args.output,
            keep_images=args.keep_images,
            dpi=args.dpi,
            retry=max(0, args.retry),
        )
    except KeyboardInterrupt:
        print("\n[INFO] 사용자 취소")
    except Exception as e:
        print(f"[ERROR] 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

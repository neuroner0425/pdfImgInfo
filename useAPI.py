import os
import re
import sys
from typing import List
from datetime import datetime

try:
    import google.generativeai as genai
except ImportError:
    print("[ERROR] google-generativeai 패키지가 설치되어 있지 않습니다.\n설치: pip install google-generativeai pillow")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("[ERROR] Pillow 패키지가 설치되어 있지 않습니다.\n설치: pip install pillow")
    sys.exit(1)

API_KEY_FILE = os.path.join(os.path.dirname(__file__), "gemini_api_key.txt")
API_KEY = None

if os.path.exists(API_KEY_FILE):
    with open(API_KEY_FILE, "r") as f:
        API_KEY = f.read().strip()

if not API_KEY:
    API_KEY = input("gemini_api_key.txt 파일이 없습니다. API 키를 입력하세요: ").strip()
    if API_KEY:
        with open(API_KEY_FILE, "w") as f:
            f.write(API_KEY)

if not API_KEY:
    print("[ERROR] API 키가 제공되지 않았습니다.")
    sys.exit(1)

MODEL_NAME_CANDIDATES = [
    "gemini-2.5-flash"
]

model = None
last_error = None
for name in MODEL_NAME_CANDIDATES:
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel(name)
        _ = model.generate_content(["ping test"], safety_settings={})
        print(f"[INFO] 모델 사용: {name}")
        break
    except Exception as e:
        last_error = e
        continue

if model is None:
    print("[ERROR] 모든 후보 모델 초기화 실패:", last_error)
    sys.exit(1)

IMAGES_PATH = "/Users/kimseunghyeon/Automator/"
OUTPUT_DIR = os.getcwd()
BATCH_SIZE = 10
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")

def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]

def load_images(paths: List[str]):
    loaded = []
    for p in paths:
        try:
            img = Image.open(p)
            loaded.append(img)
        except Exception as e:
            print(f"[WARN] 이미지 로드 실패 {p}: {e}")
    return loaded

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

def build_batch_prompt(batch_file_names: List[str]) -> str:
    header = "이 배치에 포함된 이미지 파일 이름 (참고용):\n" + "\n".join(f"- {os.path.basename(f)}" for f in batch_file_names) + "\n\n"
    return header + BASE_INSTRUCTIONS

def generate_for_batch(batch_paths: List[str]):
    file_names_sorted = sorted(batch_paths, key=natural_sort_key)
    prompt = build_batch_prompt(file_names_sorted)
    images = load_images(file_names_sorted)
    if not images:
        print("[WARN] 이미지 로드 실패로 배치 건너뜀")
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

def main():
    IMAGES_PATH = input("이미지 폴더 경로를 입력하세요 (예: /path/to/images): ").strip()
    if not os.path.isdir(IMAGES_PATH):
        print(f"[ERROR] 이미지 폴더를 찾을 수 없습니다: {IMAGES_PATH}")
        sys.exit(1)
    all_files = [os.path.join(IMAGES_PATH, f) for f in os.listdir(IMAGES_PATH) if f.lower().endswith(IMAGE_EXT)]
    if not all_files:
        print("[ERROR] 이미지 파일이 없습니다.")
        sys.exit(1)
    all_files.sort(key=lambda p: natural_sort_key(os.path.basename(p)))
    print(f"[INFO] 총 {len(all_files)}개 이미지 발견. {BATCH_SIZE}개씩 처리합니다.")
    results = []
    for i in range(0, len(all_files), BATCH_SIZE):
        batch = all_files[i:i + BATCH_SIZE]
        print(f"[INFO] 배치 처리: {i + 1} ~ {i + len(batch)} ({len(batch)}개)")
        batch_text = generate_for_batch(batch)
        if batch_text:
            if batch_text.startswith("```"):
                batch_text = batch_text.strip("`")
            results.append(batch_text)
        else:
            results.append("```\n(이 배치에서 결과를 생성하지 못했습니다.)\n```")
    final_output = "\n\n---\n\n".join(results) + "\n"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"gemini_result_{ts}.md"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_output)
    print(f"[INFO] 결과 저장: {out_path}")

if __name__ == "__main__":
    main()

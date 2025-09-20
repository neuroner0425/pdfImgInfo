"""애플리케이션 전역 설정 및 경로 관련 상수.

환경 변수 로딩과 디렉토리 준비를 담당한다.
"""
from __future__ import annotations
import os
import shutil

# ---------------- 환경 변수 ----------------
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "10"))
RETRY = int(os.environ.get("RETRY", "2"))
DPI = int(os.environ.get("DPI", "200"))
KEEP_IMAGES = os.environ.get("KEEP_IMAGES", "0") == "1"
WORKER_CONCURRENCY = int(os.environ.get("WORKER_CONCURRENCY", "4"))
MODEL_NAME_CANDIDATES = ["gemini-2.5-flash"]

# ---------------- 경로 ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # src 디렉토리
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# 최종적으로 루트 기준 디렉토리 사용
STORAGE_DIR = os.path.join(PROJECT_ROOT, "pdf_jobs")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "templates")
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")

for _d in (STORAGE_DIR, TEMPLATE_DIR, STATIC_DIR):
    os.makedirs(_d, exist_ok=True)

# 기본 프롬프트 공통 지시문
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

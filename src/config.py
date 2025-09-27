"""애플리케이션 전역 설정 및 경로 관련 상수.

환경 변수 로딩과 디렉토리 준비를 담당한다.
"""
from __future__ import annotations
import os
import shutil

# ---------------- 환경 변수 ----------------
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "15"))
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
BASE_INSTRUCTIONS = """
보낸 이미지들은 강의 자료들이고, 텍스트 자료와 시각 자료가 포함되어 있어. 용어 정리 부터 하면 '사진 파일'은 내가 보낸 이미지 사진 파일이고, '이미지'는 사진 파일 안에 있는 시각 자료 이미지다.

너의 목표는 각 사진 파일에 포함된 모든 내용을 마크다운 형식으로 보내는 것이다.
텍스트가 있다면 텍스트 원문 그대로를, 이미지가 있다면 이미지에 대한 설명을 적어줘. 사진 파일 이름은 적지 않아도 돼. 모든 답을 하나의 마크다운으로 적어주고, 답변 이외의 아무 말도 하지 마.
반복적인 단어나 문장을 생성하지 마.

텍스트는 사진 파일에 있는 `원문 그대로를 모두` 적어야한다. 임의로 줄이거나 요약하지 마. 제목 소제목 등이 있다면 h3부터 시작해서 차례로 적어줘. 그리고 목록이 있다면 '- '기호를 사용해서 나열해서 적어줘.

표(Table)를 작성할 때, **헤더와 구분선은 내용 길이에 상관없이 3개의 하이픈('-')만 사용해야 한다.** 불필요한 공백을 추가하여 시각적 정렬을 시도하지 마라.
예시: `| 헤더1 | 헤더2 |` 다음에 `|---|---|` 와 같이 3개의 하이픈만 사용해야 한다.

불필요한 이미지(반복적으로 반복하는 로고, 템플릿의 배경 등)에 대한 설명은 생략해도 된다. 하지만 이미지가 조금이라도 의미있다면 이미지에 대한 설명은 꼭 자세하게 작성해줘.

예시는 다음과 같다.

```
### 03. 네트워크 접속장치(LAN 카드)

#### 1. LAN 카드

- LAN 카드(NIC, Network Interface Card)는
- 네트워크에 연결하는

> **NOTE 확장 슬롯(extended slot)**
> 컴퓨터 본체 내부에 있는 소켓이다. 

[그림 2-10 LAN 카드(왼쪽)와 USB 무선 LAN 카드(오른쪽)]
[이미지 설명: 유선 LAN 카드와 USB 무선 LAN 카드가 나란히 놓여 있는 사진. 왼쪽은 컴퓨터 내부의 확장 슬롯에 장착되는 유선 LAN 카드(PCI Express 방식)이며, 오른쪽은 USB 포트에 꽂아 사용하는 무선 LAN 카드(동글 형태, 'Axler' 브랜드)이다.]

 #### 2. 허브

- 허브(hub)는
- 허브를 사용하면

구체적인 정보를 기술하는 방법은 다음과 같다.
> [가시성] 이름(인자1: 타입, 인자2: 타입, ...): 반환 타입

```

그리고 각 사진 파일들을 분리해서 답해주고, 사진 파일들은 두 줄 건너뜀과 "---"으로 구분해줘. 사진 파일 이름 오름차순으로 정렬해서 보내줘.
"""

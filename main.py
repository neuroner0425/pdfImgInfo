from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc
import json
import pyautogui
import os
import re
from time import sleep

cookie_path = 'cookies.json'
images_path = '/Users/kimseunghyeon/Automator/'

def init_driver():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            driver = uc.Chrome()
            sleep(1)
            driver.get('https://gemini.google.com/')  # 먼저 도메인 접속
            sleep(1)
            try:
                with open(cookie_path, 'r') as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        driver.add_cookie(cookie)
                print("쿠키 불러오기 성공!")
                driver.refresh()  # 쿠키 적용 후 새로고침
                sleep(1)
                return driver
            except FileNotFoundError:
                print("쿠키 파일이 없습니다. 로그인부터 시작합니다.")
                driver.find_element(By.XPATH,'//a[text()="로그인"]').click()
                input("로그인 후 엔터를 누르세요...")
                cookies_to_save = driver.get_cookies()
                with open(cookie_path, 'w') as f:
                    json.dump(cookies_to_save, f)
            return driver
        except Exception as e:
            if 'no such window' in str(e) or 'target window already closed' in str(e) or 'web view not found' in str(e):
                print(f"드라이버 생성/접속 오류 발생({e}), {attempt+1}회 재시도...")
                try:
                    driver.quit()
                except:
                    pass
                sleep(2)
                continue
            else:
                print("init_driver 예외:", e)
                break
    raise RuntimeError("드라이버를 정상적으로 시작할 수 없습니다.")

def change_model_to_gemini_flash(driver):
    button__label = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//span[@class="mdc-button__label"]'))
    )
    
    if button__label.text != "2.5 Flash":
        button__label.click()
        sleep(0.1)
        button_25 = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//span[text()=" 2.5 Flash "]'))
        )
        button_25.click()
        sleep(0.1)

def upload_file(driver, file_path):
    try:
        driver.find_element(By.XPATH, '//button[@aria-label="파일 업로드 메뉴 열기"]').click()
        driver.find_element(By.XPATH, '//button[@aria-label="파일 업로드. 문서, 데이터, 코드 파일"]').click()
        file_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//input[@type="file"]'))
        )
        file_input.send_keys(file_path)
        sleep(1)
        print("파일 업로드 성공!:", file_path.split('/')[-1])
    except Exception as e:
        print("파일 업로드 실패:", e)

def input_prompt_and_send(driver):
    try:
        prompt_box = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@aria-label="여기에 프롬프트 입력"]'))
        )
        prompt_box.click()
        # 메시지 입력
        ActionChains(driver).send_keys("보낸 이미지들은 강의 자료들인데, 시각 자료가 포함되어 있어. 용어 정리 부터 하면 \'파일\'은 내가 보낸 이미지 파일이고, \'이미지\'는 파일 안에 있는 시각 자료 이미지야.").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("각 파일에 포함된 모든 내용을 마크다운 `코드`로 보내줘. 텍스트가 있다면 텍스트 원문 그대로를, 이미지가 있다면 이미지에 대한 설명을 적어줘. 파일 이름은 적지 않아도 돼. 모든 답을 하나의 마크다운 코드로 적어주고, 답변 이외의 아무 말도 하지 마.").perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("텍스트는 파일에 있는 `원문 그대로를 모두` 적어줘야해. 임의로 줄이거나 요약하지 마. 제목 소제목 등이 있다면 h3부터 시작해서 차례로 적어줘. 그리고 목록이 있다면 \'-\'기호를 사용해서 나열해서 적어줘. 예시는 다음과 같아").perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("```").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("### 03. 네트워크 접속장치(LAN 카드)").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("#### 1. LAN 카드").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("- LAN 카드(NIC, Network Interface Card)는 두 대 이상의 컴퓨터로 네트워크를 구성하려고 외부 네트워크와 빠른 속도로 데이터를 송수신할 수 있게 컴퓨터 내에 설치하는 확장 카드를 말한다.").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("- 네트워크에 연결하는 물리적 장치에는 반드시 하나의 LAN 카드가 있어야 한다. LAN 카드는 전송매체에 접속하는 역할과 데이터의 입출력 및 송수신, 프로토콜의 처리 기능 등을 담당한다.").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("- 이 카드는 마더보드의 확장 슬롯에 설치하며, 네트워크 케이블을 연결하는 외부 포트를 포함하고 있다.").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("> **NOTE 확장 슬롯(extended slot)**").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("> 컴퓨터 본체 내부에 있는 소켓이다. 메모리, 하드디스크 인터페이스 보드, 그래픽 보드, 사운드 보드, LAN 보드 등의 확장 보드를 데이터 통로로 접속할 수 있도록 설계되어 있다.").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("```").key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("이미지에 대한 설명은 꼭 `자세하게` 해줘. 예시는 다음과 같아.").perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("\"[이미지 설명: 다양한 네트워크 접속 장치를 사용한 네트워크 구성도. 라우터 아래에 스위치 A와 B가 있고, 각 스위치 아래에 허브 1과 2가 연결되어 있다. 허브들은 각각 여러 컴퓨터에 연결되며, 브리지를 통해 두 네트워크 간의 무선 연결도 이루어진다.]\"").perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("만약 이미지에 대한 식별이 있다면 적어줘.").perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("\"[그림 2-9 접속 장치로 연결된 네트워크]\"").perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("그리고 각 파일들을 분리해서 답해주고, 파일들은 `\"---\"`으로 구분해줘. 파일 이름 오름차순으로 정렬해서 보내줘.").perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
        ActionChains(driver).send_keys("마크다운 코드, 꼭 코드로 보내줘.").perform()
        
        sleep(1)
        
        send_box = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//button[@aria-label="메시지 보내기"]'))
        )
        send_box.click()
        print("프롬프트 입력 성공!")
    except Exception as e:
        print("프롬프트 입력 실패:", e)
        
def wait_for_response(driver):
    try:
        # '대답 생성 중지' 버튼이 사라지고 '메시지 보내기' 버튼이 다시 나타날 때까지 대기
        WebDriverWait(driver, 100).until(
            EC.presence_of_element_located((By.XPATH, '//button[@aria-label="메시지 보내기"]'))
        )
        print("응답 생성 완료!")
    except Exception as e:
        print("응답 대기 실패:", e)

def send_image_and_prompt(driver, images):
    for image in images:
        upload_file(driver, image)
    sleep(1)
    pyautogui.press('esc')
    sleep(1)
    
    input_prompt_and_send(driver)
    wait_for_response(driver)

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def save_result(driver, filename):
    try:
        # 대화 내용 전체 선택 (Ctrl+A)
        result = ""
        chat_bodies = driver.find_elements(By.XPATH, '//response-container')
        for body in chat_bodies:
            code_bodys = body.find_element(By.TAG_NAME, 'pre')
            result += code_bodys.text + "\n\n---\n\n"
            
        filename = input("저장하려는 파일명: ") + ".md"

        # 결과를 파일로 저장
        with open(filename, 'w') as f:
            f.write(result)
        print(f"대화 내용이 '{filename}'로 저장되었습니다.")
    except Exception as e:
        print("대화 내용 저장 실패:", e)

if __name__ == "__main__":
    driver = init_driver()
    
    change_model_to_gemini_flash(driver)

    # images_path 내 이미지 파일 목록 불러오기 (jpg, png, jpeg, bmp, gif 등)
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
    all_files = os.listdir(images_path)
    images = [os.path.join(images_path, f) for f in all_files if f.lower().endswith(image_extensions)]

    # 자연스러운 오름차순 정렬 (10이 9 뒤에 오도록)
    images.sort(key=natural_sort_key)

    # 10개씩 끊어서 send_image_and_prompt 실행
    for i in range(0, len(images), 10):
        batch = images[i:i+10]
        print(f"이미지 {i+1}~{i+len(batch)}번 전송 중...")
        send_image_and_prompt(driver, images=batch)

    save_result(driver)
    
    input("종료하려면 엔터를 누르세요...")
    
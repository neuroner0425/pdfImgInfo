from pdf2image import convert_from_path
import os

def pdf_to_jpegs(pdf_path, output_folder):
    # PDF를 이미지 리스트로 변환
    images = convert_from_path(pdf_path)
    os.makedirs(output_folder, exist_ok=True)
    for i, image in enumerate(images):
        output_path = f"{output_folder}/page_{i+1}.jpeg"
        image.save(output_path, 'JPEG')
        print(f"Saved: {output_path}")

# 사용 예시
pdf_to_jpegs("test.pdf", "output_images")
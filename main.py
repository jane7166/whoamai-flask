import os
import time
import json
import re
import requests  # 이미지 다운로드를 위해 필요
import base64  # Base64 변환을 위해 필요
from bs4 import BeautifulSoup  # HTML에서 텍스트 추출
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
api_key = os.getenv("MY_KEY")

app = Flask(__name__)
CORS(app)  # CORS 허용

if not api_key:
    raise ValueError("API Key가 설정되지 않았습니다. .env 파일을 확인하세요.")

genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

def extract_text_from_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator=" ", strip=True)

def extract_images_from_html(html_content):
    return re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)

def url_to_base64(image_url):
    try:
        response = requests.get(image_url, timeout=5)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode("utf-8")
        else:
            return None
    except Exception as e:
        print(f"⚠️ 이미지 변환 실패 ({image_url}): {str(e)}")
        return None

@app.route("/process_json", methods=["POST"])
def process_blogger():
    start_time = time.time()

    try:
        data = request.get_json()  # Next.js에서 받은 전체 bloggerData
        # 여기서 data 구조는 { kind: 'blogger#postList', items: [...], ... }

        items = data.get("items", [])
        if not items:
            return jsonify({"error": "No posts found in 'items'"}), 400

        # ✅ 게시글에서 텍스트 및 이미지 추출
        all_texts = []
        all_images_base64 = []

        for post in items:
            content = post.get("content", "")
            extracted_text = extract_text_from_html(content)
            extracted_images = extract_images_from_html(content)

            all_texts.append({
                "post_id": post.get("id", "unknown"),
                "text": extracted_text
            })

            for img_url in extracted_images:
                base64_img = url_to_base64(img_url)
                if base64_img:
                    all_images_base64.append({
                        "original_url": img_url,
                        "base64": base64_img
                    })

        print("📢 Blogger 게시글 텍스트 및 이미지 변환 완료")

        # ✅ Gemini API 호출
        prompt = """
        개인이 운영하는 블로그의 게시글과 게시글에 포함된 이미지야...
        (이하 동일)
        """
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                stop_sequences=['x'],
                temperature=1.0
            )
        )

        print("Gemini API 응답:", response.text)

        # 응답을 JSON으로 파싱 시도 (JSON이 아니면 그대로 사용)
        try:
            gen_response = json.loads(response.text) if response.text.strip() else None
        except Exception as parse_error:
            print("JSON 파싱 실패:", parse_error)
            gen_response = response.text

        execution_time = time.time() - start_time

        return jsonify({
            "response": gen_response if gen_response else "No response",
            "execution_time": f"{execution_time:.2f} 초",
            "all_texts": all_texts,
            "all_images_base64": all_images_base64
        })

    except Exception as e:
        print("Error in process_blogger:", str(e))
        return jsonify({"error": "Failed to process Blogger data", "details": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

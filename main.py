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

# 환경 변수 로드
load_dotenv()
api_key = os.getenv("MY_KEY")

# Flask 앱 생성
app = Flask(__name__)
CORS(app)  # CORS 설정 (프론트엔드와 백엔드 통신 허용)

# API Key 설정
if not api_key:
    raise ValueError("API Key가 설정되지 않았습니다. .env 파일을 확인하세요.")

genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")


# ✅ Blogger API에서 게시글 가져오기
def fetch_blogger_posts(access_token, blog_id):
    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("items", [])  # 게시글 목록 반환
    else:
        print(f"⚠️ Blogger API 요청 실패: {response.status_code}")
        return []


# ✅ HTML에서 텍스트 추출 함수
def extract_text_from_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator=" ", strip=True)  # HTML 태그 제거 후 순수 텍스트 반환


# ✅ 이미지 URL에서 Base64 변환 함수
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


# ✅ 게시글 내용에서 이미지 URL 추출 함수
def extract_images_from_html(html_content):
    return re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)  # 정규식으로 이미지 URL 찾기


# ✅ Blogger 게시글을 가져와서 Gemini에게 전달하는 엔드포인트
@app.route("/process_blogger", methods=["POST"])
def process_blogger():
    start_time = time.time()

    try:
        # ✅ 사용자의 액세스 토큰과 블로그 ID 받기
        data = request.get_json()
        access_token = data.get("access_token")
        blog_id = data.get("blog_id")

        if not access_token or not blog_id:
            return jsonify({"error": "Access token or Blog ID missing"}), 400

        # ✅ Blogger API에서 게시글 가져오기
        posts = fetch_blogger_posts(access_token, blog_id)

        # ✅ 게시글에서 텍스트 및 이미지 추출
        all_texts = []
        all_images_base64 = []

        for post in posts:
            content = post.get("content", "")
            extracted_text = extract_text_from_html(content)
            extracted_images = extract_images_from_html(content)

            # ✅ 텍스트 추가
            all_texts.append({"post_id": post.get("id", "unknown"), "text": extracted_text})

            # ✅ 이미지 Base64 변환 후 추가
            for img_url in extracted_images:
                base64_img = url_to_base64(img_url)
                if base64_img:
                    all_images_base64.append({"original_url": img_url, "base64": base64_img})

        print("📢 Blogger 게시글 텍스트 및 이미지 변환 완료")

        # ✅ Gemini에게 분석 요청 (Blogger 게시글 포함)
        prompt = f"""
        개인이 운영하는 블로그의 게시글과 게시글에 포함된 이미지야. 블로그 운영자의 게시글과 이미지를 통해 개인을 추측할 수 있는지 평가하고 개인정보 유출 위험도를 최대한 분석할거야.

- 특정 조건에서 개인정보 유출 가능성이 있는 경우 어떤 게시글이나 이미지를 보고 그렇게 판단했는지 그 근거와 함께 어떤 정보를 어떻게 예측할 수 있는지 설명할 수 있어야 해.
- 직접적인 언급이 없더라도 다양한 정보를 통해 유추할 수 있는 내용도 개인정보로 포함할거야. 
- 게시물과 이미지의 정보를 종합해서 예측해줘. 
예를 들어 나이를 언급하고 있지 않아도 최근 고등학교 졸업과 관련된 내용이 게시글에 포함되어있다면 20대 초반으로 예측해줘.
- 특히 주변의 정보들과 혼동되지 않고 블로그 운영자 본인의 개인정보만 예측해야 해. 
예를 들어 특정 음식점의 전화번호, 지인의 이름과 같은 정보는 블로그 운영자의 정보가 아니야.

답변은 JSON 형식으로 해줘.
id는 1.1, 1.2와 같이 질문 번호를, question에는 직접적인 질문, answer에는 질문에 대한 답변을, evidence에는 제미나이가 생각하는 답변에 대한 근거를, source_texts에는 어떤 블로그 게시글의 문장을 보고 그렇게 판단했는 지를, source_images에는 어떤 이미지를 보고 그렇게 판단했는지에 대해 JSON 형식으로 반환해주면 돼.

예시는 다음과 같아.

{
      "id": "1.1",
      "question": "블로그 운영자의 이름은 무엇인가?",
      "answer": "김철수",
      "evidence": "여러 게시글에서 '철수형'이라는 별칭이 반복적으로 등장하며, 특정 게시글에서 본명이 노출됨",
      "source_texts": [
        "오늘 영희가 나를 실수로 철수형이라고 불렀다.",
        "오늘 길동이 형과 약속이 있었다."
      ],
      "source_images": [
        "https://example.com/image1.jpg",
        "https://example.com/image2.jpg"
      ]
}
평가할 개인정보는 아래 1.부터 5.까지의 조건들에 따라 평가해줘.

1. 블로그 운영자의 개인 신상 정보 유출 가능성 평가
1.1 블로그 운영자의 이름은 무엇인가?
- 운영자의 이름이 언급되어 있는가?
- 언급되어 있지 않더라도 특정 닉네임, 별명, 애칭, SNS ID나 게임ID를 통해 이름이 추론 가능한가?
1.2 블로그 운영자의 성별은 무엇인가?
- 운영자의 성별이 언급되어 있는가?
- 이모티콘, 문체, 게시글에서 언급된 특정 단어, 또는 피드에 자주 등장하는 인물 분석을 통해 성별을 유추할 수 있는가?
1.3 블로그 운영자의 나이와 생년월일은 무엇인가? 
- 운영자의 나이, 생년월일이 언급되어 있는가?
- 특정 학교, 학력, 직업, 경험을 통해 연령대를 추론할 수 있는가?
1.4 운영자의 본인의 전화번호 또는 카드번호 또는 여권번호 또는 자동차 번호 또는 특정 비밀번호는 무엇인가?
- 1.4에 포함된 운영자의 정보가 언급되거나 노출되었는가?
- 1.4에 포함된 운영자의 정보가 일부라도 노출되었는가?
1.5 블로그 운영자의 거주지는 어디인가?
- 블로그 운영자의 거주지가 직접적으로 언급되거나 노출되었는가?
- 게시글의 내용 또는 이미지 배경(거리, 랜드마크, 특정 지역 상호명)을 통해 거주지를 유추할 수 있는가? 그 지역이 여행지가 아닌 거주지라고 추론할 수 있는가?

2. 건강 및 의료 정보 유출 여부
2.1 블로그 운영자가 앓고 있는 질병은 무엇인가?
- 블로그 운영자가 앓고 있는 질병을 언급하거나 노출되었는가?
- 병원 방문 기록, 약 처방 내역 등을 통해 건강 상태를 유추할 수 있는가?
2.2 블로그 운영자의 장애 유무는 무엇인가?
- 블로그 운영자가 앓고 있는 질병을 언급하거나 노출되었는가?
- 병원 방문 기록, 약 처방 내역 등을 통해 건강 상태를 유추할 수 있는가?
2.3 블로그 운영자의 건강 상태는 어떠한가?
- 블로그 운영자가 앓고 있는 질병을 언급하거나 노출되었는가?
- 병원 방문 기록, 약 처방 내역 등을 통해 건강 상태를 유추할 수 있는가?

3. 위치 및 출입 정보 유출 여부
3.1 블로그 운영자가 자주 방문하는 장소는 어디인가?
- 블로그 운영자가 자주 방문하는 장소(카페, 헬스장, 회사, 학교 등)가 노출되었는가?
3.2 블로그 운영자의 직장 위치는 어디인가?
- 블로그 운영자의 출퇴근 경로가 언급되거나 노출되었는가? 이를 통해 직장의 위치를 유추할 수 있는가?
- 블로그 운영자의 직장이 언급되거나 노출되었는가?

4. 사회적 신분 관련 정보
4.1 블로그 운영자의 학력은 무엇인가?
- 블로그 운영자의 학교 및 학력이 언급되었거나 노출되었는가?
- 학교명, 입학 또는 졸업 연도 등을 통해 학력을 유추할 수 있는가?
4.2 블로그 운영자의 전공이나 직업은 무엇인가?
- 블로그 운영자의 전공이나 직업이 직접 언급되었거나 유추 가능한가?
4.3 블로그 운영자의 가족 관계는 어떻게 되는가?
- 블로그 운영자의 가족에 대한 언급이나 노출 되었는가?
4.4 블로그 운영자의 종교는 무엇인가?
- 블로그 운영자가 다니는 종교 시설이 언급되었거나 노출되었는가?
- 블로그 운영자가 자신의 종교에 대해 언급하였는가?
- 블로그 운영자의 종교적인 발언을 통해 종교를 예측할 수 있는가?
4.5 블로그 운영자의 정치 성향은 무엇인가?
- 블로그 운영자가 자신의 정치적 성향에 대해 언급하였는가?
- 블로그 운영자가 정치적인 상황에 대해 언급한 적이 있는가? 이를 통해 정치 성향을 알 수 있는가?

5. 취미 및 관심사 노출
5.1 블로그 운영자의 소비 패턴은 어떠한가?
- 블로그 운영자가 어떤 브랜드, 가게 등을 노출했는가? 이를 통해 소비 패턴을 알 수 있는가?
- 블로그 운영자가 가장 많이 소비하는 분야는 무엇인가?
5.2 블로그 운영자의 취미 생활은 무엇인가?
- 블로그 운영자가 자주 방문하는 곳이나, 소비패턴, 하는 활동 등을 고려하여 취미 생활을 알 수 있는가?
5.3 블로그 운영자의 반려동물의 정보는 무엇인가?
- 블로그 운영자가 자신의 반려 동물을 언급하거나 노출하였는가?
- 지인의 반려동물이 아닌 블로그 운영자의 반려동물임을 알 수 있는가?
        """

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                stop_sequences=['x'],
                temperature=1.0
            )
        )

        execution_time = time.time() - start_time

        return jsonify({
            "response": response.text if response else "No response",
            "execution_time": f"{execution_time:.2f} 초",
            "all_texts": all_texts,
            "all_images_base64": all_images_base64
        })

    except Exception as e:
        return jsonify({"error": "Failed to process Blogger data", "details": str(e)}), 500


# 서버 실행
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

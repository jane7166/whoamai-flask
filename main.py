import os
import time
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

# 환경변수 로드
load_dotenv()
api_key = os.getenv('MY_KEY')

# Flask 앱 생성
app = Flask(__name__)
CORS(app)  # CORS 설정 (프론트와 백엔드 통신 허용)

# API Key 설정
if not api_key:
    raise ValueError("API Key가 설정되지 않았습니다. .env 파일을 확인하세요.")

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

# 고정된 질문 설정
DEFAULT_PROMPT = "모든 대답은 한국어로 대답해줘. 1+1이 뭐야?"

# API 엔드포인트 (프론트에서 호출할 곳)
@app.route("/generate", methods=["GET"])
def generate():
    start_time = time.time()

    response = model.generate_content(
        DEFAULT_PROMPT,
        generation_config=genai.types.GenerationConfig(
            candidate_count=1,
            stop_sequences=['x'],
            temperature=1.0
        )
    )

    execution_time = time.time() - start_time  # 실행 시간 측정 종료

    if response and response.text:
        return jsonify({
            "response": response.text,
            "execution_time": f"{execution_time:.2f} 초"
        })
    else:
        return jsonify({"error": "Failed to generate response."}), 500

# 서버 실행
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

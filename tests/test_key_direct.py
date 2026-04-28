import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'libs'))
import google.generativeai as genai
from src.common.config_utils import load_config
import signal

def handler(signum, frame):
    raise Exception("API Timeout!")

signal.signal(signal.SIGALRM, handler)
signal.alarm(10) # 10秒超时

config = load_config()
key = config.get("GOOGLE_API_KEY")

if not key:
    print("No Key")
    sys.exit(1)

genai.configure(api_key=key)

try:
    print(f"Direct testing key: {key[:10]}... (10s timeout)")
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Hi")
    print(f"SUCCESS: {response.text}")
except Exception as e:
    print(f"FAILED or TIMEOUT: {e}")

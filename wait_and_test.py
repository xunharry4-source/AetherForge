import time
import subprocess
import requests

print("Polling for API server on http://127.0.0.1:5006...")
for i in range(120): # wait up to 2 minutes
    try:
        res = requests.get("http://127.0.0.1:5006/api/system/health", timeout=1)
        if res.status_code == 200:
            print("\n✅ API Server is UP! Running test suite...\n")
            subprocess.run(["test_venv/bin/python", "tests/clinical_api_requests_test.py"])
            break
    except requests.exceptions.ConnectionError:
        pass
    time.sleep(2)
else:
    print("API Server did not start within 2 minutes.")

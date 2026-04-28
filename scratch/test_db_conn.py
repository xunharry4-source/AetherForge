import pymongo
import sys

def test_conn(uri):
    print(f"Testing {uri}...")
    try:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        print(f"  - SUCCESS: Connected to {uri}")
        return True
    except Exception as e:
        print(f"  - FAILED: {e}")
        return False

if __name__ == "__main__":
    test_conn("mongodb://localhost:27017/")
    test_conn("mongodb://127.0.0.1:27017/")
    test_conn("mongodb://[::1]:27017/")

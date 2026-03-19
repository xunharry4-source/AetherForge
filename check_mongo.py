import pymongo

def list_dbs():
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    try:
        print(f"Databases: {client.list_database_names()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_dbs()

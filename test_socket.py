import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(('localhost', 50005))
    print("Success")
except Exception as e:
    print(f"Error: {e}")
finally:
    s.close()

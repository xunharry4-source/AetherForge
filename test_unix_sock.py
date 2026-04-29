import socket
import os

sock_path = '/tmp/test_sock.sock'
if os.path.exists(sock_path):
    os.remove(sock_path)

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(sock_path)
    print("Successfully bound to Unix socket!")
except Exception as e:
    import traceback
    traceback.print_exc()

from flask import Flask
app = Flask(__name__)
@app.route('/')
def hello():
    return "Hello World"
if __name__ == '__main__':
    app.run(port=15005, host='127.0.0.1')

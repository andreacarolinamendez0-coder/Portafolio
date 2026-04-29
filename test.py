print("inicio")
from flask import Flask
print("flask ok")
app = Flask(__name__)
print("app ok")

@app.route('/')
def index():
    return "hola"

print("antes de run")
app.run(port=5000)
print("despues de run")
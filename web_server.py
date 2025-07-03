from flask import Flask, send_from_directory

app = Flask(__name__)

@app.route("/")
def root():
    return "✅ Serveur Flask actif. Va sur /live"

@app.route("/live")
def serve_novnc():
    return send_from_directory("novnc", "vnc.html")

@app.route("/<path:path>")
def serve_files(path):
    return send_from_directory("novnc", path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
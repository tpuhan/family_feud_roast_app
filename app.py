
import json
import os
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit

# ---- Config ----
APP_SECRET = os.environ.get("FEUD_SECRET", "super-secret-key")
PORT = int(os.environ.get("PORT", "3000"))

app = Flask(__name__)
app.config["SECRET_KEY"] = APP_SECRET
# Using eventlet if available, else falls back to threading
socketio = SocketIO(app, cors_allowed_origins="*")

# ---- Load questions ----
QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), "questions.json")

def load_questions():
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

QUESTIONS = load_questions()

# ---- Game State ----
def default_state():
    return {
        "question_index": 0,
        "revealed": [],  # list[bool] same length as answers in current question
        "strikes": 0,
        "scores": {"Team A": 0, "Team B": 0}
    }

state = default_state()

def clamp_question_index(idx):
    return max(0, min(idx, len(QUESTIONS) - 1))

def current_question():
    return QUESTIONS[state["question_index"]]

def rebuild_revealed():
    n = len(current_question()["answers"])
    if len(state["revealed"]) != n:
        state["revealed"] = [False] * n

def broadcast_state():
    # Build payload that includes the current question content (without hiding anything; reveal is handled by flags)
    payload = {
        "question_index": state["question_index"],
        "question_total": len(QUESTIONS),
        "question": current_question()["question"],
        "answers": current_question()["answers"],  # [{text, points}]
        "revealed": state["revealed"],
        "strikes": state["strikes"],
        "scores": state["scores"],
    }
    socketio.emit("update_state", payload)

@app.route("/")
def audience():
    # Big screen & phone viewers see the same audience board
    return render_template("index.html")

@app.route("/controller")
def controller():
    # Host control panel
    return render_template("controller.html")

@app.route("/health")
def health():
    return "ok"

# Optional route to serve the raw questions file (not strictly needed)
@app.route("/questions.json")
def qfile():
    return send_from_directory(os.path.dirname(QUESTIONS_PATH), "questions.json")

# ---- SocketIO events ----
@socketio.on("connect")
def on_connect():
    rebuild_revealed()
    broadcast_state()

@socketio.on("request_state")
def on_request_state():
    rebuild_revealed()
    broadcast_state()

@socketio.on("set_question")
def on_set_question(data):
    idx = int(data.get("index", 0))
    state["question_index"] = clamp_question_index(idx)
    state["strikes"] = 0
    rebuild_revealed()
    broadcast_state()

@socketio.on("next_question")
def on_next_question():
    state["question_index"] = clamp_question_index(state["question_index"] + 1)
    state["strikes"] = 0
    rebuild_revealed()
    broadcast_state()

@socketio.on("prev_question")
def on_prev_question():
    state["question_index"] = clamp_question_index(state["question_index"] - 1)
    state["strikes"] = 0
    rebuild_revealed()
    broadcast_state()

@socketio.on("reveal_answer")
def on_reveal_answer(data):
    i = int(data.get("i", -1))
    rebuild_revealed()
    if 0 <= i < len(state["revealed"]):
        state["revealed"][i] = True
        broadcast_state()

@socketio.on("hide_answer")
def on_hide_answer(data):
    i = int(data.get("i", -1))
    rebuild_revealed()
    if 0 <= i < len(state["revealed"]):
        state["revealed"][i] = False
        broadcast_state()

@socketio.on("reveal_all")
def on_reveal_all():
    rebuild_revealed()
    for i in range(len(state["revealed"])):
        state["revealed"][i] = True
    broadcast_state()

@socketio.on("reset_reveals")
def on_reset_reveals():
    state["revealed"] = [False] * len(current_question()["answers"])
    broadcast_state()

@socketio.on("add_strike")
def on_add_strike():
    state["strikes"] = min(3, state["strikes"] + 1)
    broadcast_state()

@socketio.on("remove_strike")
def on_remove_strike():
    state["strikes"] = max(0, state["strikes"] - 1)
    broadcast_state()

@socketio.on("award_points")
def on_award_points(data):
    team = data.get("team", "Team A")
    pts = int(data.get("points", 0))
    if team not in state["scores"]:
        return
    state["scores"][team] += pts
    broadcast_state()

@socketio.on("set_scores")
def on_set_scores(data):
    # Optional: directly set scores (e.g., reset)
    a = int(data.get("A", state["scores"]["Team A"]))
    b = int(data.get("B", state["scores"]["Team B"]))
    state["scores"]["Team A"] = a
    state["scores"]["Team B"] = b
    broadcast_state()

if __name__ == "__main__":
    # Tips:
    #   pip install flask flask-socketio eventlet
    #   python app.py
    # Then open http://localhost:5000 (audience), http://localhost:5000/controller (host)
    socketio.run(app, host="0.0.0.0", port=PORT, debug=True)

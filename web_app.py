from flask import Flask, render_template, request, redirect, session, jsonify
from pymongo import MongoClient
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
import json, os

app = Flask(__name__)
app.secret_key = "namhome_secret"

# ================== CONFIG ==================
BROKER = "broker.emqx.io"
MONGO_URI = "mongodb+srv://smarthome_user:123@cluster0.3s47ygi.mongodb.net/"

mongo = MongoClient(MONGO_URI)
db = mongo["smarthome"]
users_col = db["users"]
logs_col = db["logs"]

last_status = {"result": "--"}

# ================== MQTT LOGIC ==================
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print("🌍 WEB MQTT CONNECTED:", rc)
    client.subscribe("namhome/+/status")

def on_message(client, userdata, msg):
    global last_status
    try:
        last_status = json.loads(msg.payload.decode())
        print("🌍 WEB RECEIVED STATUS:", last_status)
    except Exception as e:
        print("Error decoding MQTT:", e)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, 1883, 60)
mqtt_client.loop_start()

# ================== ROUTES ==================
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        user = users_col.find_one({"username": u, "password": p})
        if user:
            session["user"] = u
            session["role"] = user["role"]
            return redirect("/dashboard")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("dashboard.html", user=session["user"], role=session["role"])

@app.route("/status")
def status():
    return jsonify(last_status)

@app.route("/door", methods=["POST"])
def door():
    publish.single("namhome/door/cmd", json.dumps({"user":session["user"]}), hostname=BROKER)
    return "OK"

@app.route("/light", methods=["POST"])
def light():
    state = request.form["state"]
    publish.single("namhome/light/cmd", json.dumps({"user":session["user"], "state":state}), hostname=BROKER)
    return "OK"

@app.route("/logs")
def logs():
    if "user" not in session: return redirect("/")
    data = list(logs_col.find({},{"_id":0}).sort("time",-1).limit(50))
    return render_template("logs.html", logs=data)

# Quản lý User (Admin only)
@app.route("/users")
def users_list():
    if session.get("role") != "admin": return "No permission"
    return render_template("users.html", users=list(users_col.find({},{"_id":0})))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

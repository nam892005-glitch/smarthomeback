from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
import json, os

app = Flask(__name__)
CORS(app)

# ================== CONFIG ==================
BROKER = "broker.emqx.io"

MONGO_URI = "mongodb+srv://smarthome_user:123@cluster0.3s47ygi.mongodb.net/"
mongo = MongoClient(MONGO_URI)
db = mongo["smarthome"]
users_col = db["users"]

last_status = {"result": "--"}

# ================== MQTT RECEIVE ==================
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print("🌍 MQTT CONNECTED:", rc)
    client.subscribe("namhome/+/status")

def on_message(client, userdata, msg):
    global last_status
    try:
        payload = msg.payload.decode()

        try:
            data = json.loads(payload)
        except:
            data = {"result": payload}

        last_status = data
        print("📩 STATUS:", data)

    except Exception as e:
        print("❌ MQTT ERROR:", e)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, 1883, 60)
mqtt_client.loop_start()

# ================== LOGIN ==================
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user = users_col.find_one({
        "username": data.get("username"),
        "password": data.get("password")
    })

    if user:
        return jsonify({
            "success": True,
            "user": user["username"],
            "role": user.get("role", "user")
        })
    return jsonify({"success": False})

# ================== CONTROL ==================
@app.route("/door", methods=["POST"])
def door():
    data = request.json or {}

    publish.single(
        "namhome/door/cmd",
        json.dumps({
            "action": "OPEN",
            "user": data.get("user", "unknown")
        }),
        hostname=BROKER,
        port=1883
    )

    return jsonify({"success": True})

@app.route("/light", methods=["POST"])
def light():
    data = request.json or {}
    state = data.get("state", "OFF")

    publish.single(
        "namhome/light/cmd",
        json.dumps({
            "state": state,
            "user": data.get("user", "unknown")
        }),
        hostname=BROKER,
        port=1883
    )

    return jsonify({"success": True})

# ================== STATUS ==================
@app.route("/status")
def status():
    return jsonify(last_status)

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

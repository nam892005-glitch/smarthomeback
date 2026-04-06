from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
from datetime import datetime
import json, os

app = Flask(__name__)
CORS(app)

# ================== CONFIG ==================
BROKER = "broker.emqx.io"

MONGO_URI = "mongodb+srv://smarthome_user:123@cluster0.3s47ygi.mongodb.net/"
mongo = MongoClient(MONGO_URI)

db = mongo["smarthome"]
users_col = db["users"]
logs_col = db["logs"]

last_status = {"result": "--"}

# ================== MQTT ==================
mqtt_client = mqtt.Client(protocol=mqtt.MQTTv311)

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
@app.route("/index", methods=["POST"])
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
@app.route("/light", methods=["POST"])
def light():
    data = request.json or {}
    state = data.get("state", "OFF")
    user = data.get("user", "unknown")

    # 👉 gửi xuống ESP32 (CHỈ ON/OFF)
    publish.single(
        "namhome/light/cmd",
        state,
        hostname=BROKER,
        port=1883
    )

    print("📤 SENT TO ESP32:", state)

    # 👉 lưu log
    logs_col.insert_one({
        "user": user,
        "device": "light",
        "action": state,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    return jsonify({"success": True})


@app.route("/door", methods=["POST"])
def door():
    data = request.json or {}
    user = data.get("user", "unknown")

    publish.single(
        "namhome/door/cmd",
        "OPEN",
        hostname=BROKER,
        port=1883
    )

    print("📤 SENT TO ESP32: OPEN")

    logs_col.insert_one({
        "user": user,
        "device": "door",
        "action": "OPEN",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    return jsonify({"success": True})

# ================== STATUS ==================
@app.route("/status")
def status():
    return jsonify(last_status)

# ================== LOGS ==================
@app.route("/logs")
def get_logs():
    data = list(logs_col.find({}, {"_id": 0}).sort("time", -1).limit(50))
    return jsonify({"logs": data})

# ================== USERS ==================
@app.route("/users")
def get_users():
    data = list(users_col.find({}, {"_id": 0}))
    return jsonify({"users": data})

@app.route("/add_user", methods=["POST"])
def add_user():
    data = request.json

    users_col.insert_one({
        "username": data["username"],
        "password": data["password"],
        "role": data["role"]
    })

    return jsonify({"success": True})

@app.route("/delete/<username>", methods=["DELETE"])
def delete_user(username):
    users_col.delete_one({"username": username})
    return jsonify({"success": True})

# ================== INIT ADMIN ==================
@app.route("/seed_admin")
def seed_admin():
    users_col.update_one(
        {"username": "admin"},
        {"$set": {
            "username": "admin",
            "password": "123456",
            "role": "admin"
        }},
        upsert=True
    )
    return "Admin created: admin / 123456"

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

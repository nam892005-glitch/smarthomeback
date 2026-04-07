from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta, timezone
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

# ================== TIME HELPER ==================
def get_vn_time():
    # Ép múi giờ GMT+7 chuẩn Việt Nam
    tz_vn = timezone(timedelta(hours=7))
    return datetime.now(tz_vn).strftime("%Y-%m-%d %H:%M:%S")

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
    except Exception as e:
        print("❌ MQTT ERROR:", e)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, 1883, 60)
mqtt_client.loop_start()

# ================== LOGIN ==================
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
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
    data = request.get_json(force=True) or {}
    state = data.get("state", "OFF")
    
    # Kiểm tra kỹ giá trị user từ Dashboard gửi lên
    user_name = data.get("user")
    if not user_name or user_name == "undefined" or user_name == "null":
        user_name = "unknown"

    # Gửi lệnh MQTT xuống ESP32
    publish.single("namhome/light/cmd", state, hostname=BROKER, port=1883)

    # Lưu log với giờ Việt Nam
    logs_col.insert_one({
        "user": user_name,
        "device": "light",
        "action": state,
        "time": get_vn_time()
    })
    return jsonify({"success": True})

@app.route("/door", methods=["POST"])
def door():
    data = request.get_json(force=True) or {}
    
    # Kiểm tra kỹ giá trị user
    user_name = data.get("user")
    if not user_name or user_name == "undefined" or user_name == "null":
        user_name = "unknown"

    publish.single("namhome/door/cmd", "OPEN", hostname=BROKER, port=1883)

    # Lưu log với giờ Việt Nam
    logs_col.insert_one({
        "user": user_name,
        "device": "door",
        "action": "OPEN",
        "time": get_vn_time()
    })
    return jsonify({"success": True})

# ================== STATUS/LOGS/USERS ==================
@app.route("/status")
def status():
    return jsonify(last_status)

@app.route("/logs", methods=["GET"])
def get_logs():
    # Lấy 50 log mới nhất
    data = list(logs_col.find({}, {"_id": 0}).sort("time", -1).limit(50))
    return jsonify({"logs": data})

@app.route("/users")
def get_users():
    data = list(users_col.find({}, {"_id": 0}))
    return jsonify({"users": data})

@app.route("/add_user", methods=["POST"])
def add_user():
    data = request.get_json(force=True) or {}
    users_col.insert_one({
        "username": data.get("username"),
        "password": data.get("password"),
        "role": data.get("role", "user")
    })
    return jsonify({"success": True})

@app.route("/delete/<username>", methods=["DELETE"])
def delete_user(username):
    users_col.delete_one({"username": username})
    return jsonify({"success": True})

@app.route("/seed_admin")
def seed_admin():
    users_col.update_one(
        {"username": "admin"},
        {"$set": {"username": "admin", "password": "123", "role": "admin"}},
        upsert=True
    )
    return "Admin created: admin / 123"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

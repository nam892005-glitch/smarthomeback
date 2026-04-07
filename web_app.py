from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
from datetime import datetime
import json, os

app = Flask(__name__)
CORS(app) # Cho phép Frontend (GitHub/Local) truy cập API

# ================== CONFIG ==================
BROKER = "broker.emqx.io"

# Đảm bảo kết nối MongoDB chính xác
MONGO_URI = "mongodb+srv://smarthome_user:123@cluster0.3s47ygi.mongodb.net/"
mongo = MongoClient(MONGO_URI)

db = mongo["smarthome"]
users_col = db["users"] # Tên collection: users
logs_col = db["logs"]   # Tên collection: logs

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
        print("📩 STATUS RECEIVED:", data)
    except Exception as e:
        print("❌ MQTT ERROR:", e)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, 1883, 60)
mqtt_client.loop_start()

# ================== LOGIN ==================
@app.route("/login", methods=["POST"])
def login():
    # request.get_json(force=True) giúp tránh lỗi khi Frontend không gửi đúng header
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
    user_name = data.get("user", "unknown") # Lấy user từ Frontend gửi lên

    # Gửi xuống ESP32
    publish.single(
        "namhome/light/cmd",
        state,
        hostname=BROKER,
        port=1883
    )

    # Lưu log - Quan trọng: đảm bảo 'user' có giá trị để không bị 'unknown'
    logs_col.insert_one({
        "user": user_name,
        "device": "light",
        "action": state,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    return jsonify({"success": True})

@app.route("/door", methods=["POST"])
def door():
    data = request.get_json(force=True) or {}
    user_name = data.get("user", "unknown")

    publish.single(
        "namhome/door/cmd",
        "OPEN",
        hostname=BROKER,
        port=1883
    )

    logs_col.insert_one({
        "user": user_name,
        "device": "door",
        "action": "OPEN",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    return jsonify({"success": True})

# ================== STATUS ==================
@app.route("/status")
def status():
    return jsonify(last_status)

# ================== LOGS (Dữ liệu cho log.html) ==================
@app.route("/logs")
def get_logs():
    # Trả về mảng dưới key "logs" để khớp với data.logs.forEach ở Frontend
    data = list(logs_col.find({}, {"_id": 0}).sort("time", -1).limit(50))
    return jsonify({"logs": data})

# ================== USERS (Dữ liệu cho user.html) ==================
@app.route("/users")
def get_users():
    # Trả về mảng dưới key "users" để khớp với data.users.forEach ở Frontend
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

# ================== INIT ADMIN ==================
@app.route("/seed_admin")
def seed_admin():
    users_col.update_one(
        {"username": "admin"},
        {"$set": {
            "username": "admin",
            "password": "123", # Đã sửa mật khẩu cho ngắn gọn theo ý bạn
            "role": "admin"
        }},
        upsert=True
    )
    return "Admin created: admin / 123"

# ================== RUN ==================
if __name__ == "__main__":
    # Dùng port từ biến môi trường của Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

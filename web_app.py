from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
from datetime import datetime
import json, os

app = Flask(__name__)
CORS(app) # Quan trọng để Frontend không bị chặn

# ================== CONFIG ==================
BROKER = "broker.emqx.io"
MONGO_URI = "mongodb+srv://smarthome_user:123@cluster0.3s47ygi.mongodb.net/"

mongo = MongoClient(MONGO_URI)
db = mongo["smarthome"]
users_col = db["users"]
logs_col = db["logs"]

# ================== ROUTES ==================

# ĐĂNG NHẬP
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
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

# ĐIỀU KHIỂN THIẾT BỊ
@app.route("/control", methods=["POST"])
def control():
    data = request.get_json(force=True)
    device = data.get("device") # 'light' hoặc 'door'
    action = data.get("action") # 'ON', 'OFF', 'OPEN'
    user_name = data.get("user", "unknown")

    # Gửi lệnh xuống MQTT - Khớp với topic ESP32 đang chờ
    topic = f"namhome/{device}/esp"
    publish.single(topic, action, hostname=BROKER, port=1883)

    # Lưu log vào MongoDB
    logs_col.insert_one({
        "user": user_name,
        "device": device,
        "action": action,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    return jsonify({"success": True})

# LẤY DANH SÁCH LOGS
@app.route("/logs")
def get_logs():
    data = list(logs_col.find({}, {"_id": 0}).sort("time", -1).limit(50))
    return jsonify({"logs": data})

# LẤY DANH SÁCH USERS
@app.route("/users")
def get_users():
    data = list(users_col.find({}, {"_id": 0}))
    return jsonify({"users": data})

# THÊM/XOÁ USER
@app.route("/add_user", methods=["POST"])
def add_user():
    data = request.get_json(force=True)
    users_col.insert_one(data)
    return jsonify({"success": True})

@app.route("/delete/<username>", methods=["DELETE"])
def delete_user(username):
    users_col.delete_one({"username": username})
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

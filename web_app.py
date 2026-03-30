from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
import json, os

app = Flask(__name__)
CORS(app)  # ✅ cho phép Netlify gọi API

# ================== CONFIG ==================
BROKER = "broker.emqx.io"

MONGO_URI = "mongodb+srv://smarthome_user:123@cluster0.3s47ygi.mongodb.net/"
mongo = MongoClient(MONGO_URI)
db = mongo["smarthome"]
users_col = db["users"]
logs_col = db["logs"]

last_status = {"result": "--"}

# ================== MQTT RECEIVE ==================
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print("🌍 MQTT CONNECTED:", rc)
    client.subscribe("namhome/+/status")

def on_message(client, userdata, msg):
    global last_status
    try:
        last_status = json.loads(msg.payload.decode())
    except:
        last_status = {"result": msg.payload.decode()}

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, 1883, 60)
mqtt_client.loop_start()

# ================== LOGIN API ==================
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
        json.dumps({"user": data.get("user", "web")}),
        hostname=BROKER, port=1883
    )
    return jsonify({"success": True})

@app.route("/light", methods=["POST"])
def light():
    data = request.json
    publish.single(
        "namhome/light/cmd",
        json.dumps({
            "user": data.get("user", "web"),
            "state": data.get("state")
        }),
        hostname=BROKER, port=1883
    )
    return jsonify({"success": True})

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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

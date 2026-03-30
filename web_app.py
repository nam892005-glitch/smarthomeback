from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
import json, os

import jwt
import datetime
import bcrypt

app = Flask(__name__)
CORS(app)

# ===== CONFIG =====
BROKER = "broker.emqx.io"
SECRET_KEY = "super_secret_key_123"

MONGO_URI = "mongodb+srv://smarthome_user:123@cluster0.3s47ygi.mongodb.net/"
mongo = MongoClient(MONGO_URI)

db = mongo["smarthome"]
users_col = db["users"]
logs_col = db["logs"]

last_status = {"result": "--"}

# ===== MQTT =====
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
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

# ===== AUTH =====
def check_auth(request):
    token = request.headers.get("Authorization")
    if not token:
        return None
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except:
        return None

# ===== LOGIN =====
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user = users_col.find_one({"username": data.get("username")})

    if user and bcrypt.checkpw(data.get("password").encode(), user["password"]):
        token = jwt.encode({
            "user": user["username"],
            "role": user.get("role", "user"),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=5)
        }, SECRET_KEY, algorithm="HS256")

        return jsonify({
            "success": True,
            "token": token,
            "user": user["username"],
            "role": user.get("role", "user")
        })

    return jsonify({"success": False})

# ===== CONTROL =====
@app.route("/door", methods=["POST"])
def door():
    user = check_auth(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    publish.single("namhome/door/cmd",
                   json.dumps({"user": user["user"]}),
                   hostname=BROKER, port=1883)

    logs_col.insert_one({
        "user": user["user"],
        "action": "open door",
        "time": str(datetime.datetime.now())
    })

    return jsonify({"success": True})

@app.route("/light", methods=["POST"])
def light():
    user = check_auth(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json

    publish.single("namhome/light/cmd",
                   json.dumps({
                       "user": user["user"],
                       "state": data.get("state")
                   }),
                   hostname=BROKER, port=1883)

    logs_col.insert_one({
        "user": user["user"],
        "action": "light " + str(data.get("state")),
        "time": str(datetime.datetime.now())
    })

    return jsonify({"success": True})

# ===== STATUS =====
@app.route("/status")
def status():
    return jsonify(last_status)

# ===== LOGS =====
@app.route("/logs")
def logs():
    user = check_auth(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = list(logs_col.find({}, {"_id": 0}).sort("time", -1).limit(50))
    return jsonify({"logs": data})

# ===== USERS =====
@app.route("/users")
def users():
    user = check_auth(request)
    if not user or user["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403

    data = list(users_col.find({}, {"_id": 0, "password": 0}))
    return jsonify({"users": data})

@app.route("/add_user", methods=["POST"])
def add_user():
    user = check_auth(request)
    if not user or user["role"] != "admin":
        return jsonify({"error": "Admin only"}), 403

    data = request.json

    hashed = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt())

    users_col.insert_one({
        "username": data["username"],
        "password": hashed,
        "role": data["role"]
    })

    return jsonify({"success": True})

@app.route("/delete/<username>", methods=["DELETE"])
def delete(username):
    user = check_auth(request)
    if not user or user["role"] != "admin":
        return jsonify({"error": "Admin only"}), 403

    users_col.delete_one({"username": username})
    return jsonify({"success": True})

# ===== SEED ADMIN =====
@app.route("/seed_admin")
def seed():
    password = bcrypt.hashpw("123456".encode(), bcrypt.gensalt())

    users_col.update_one(
        {"username": "admin"},
        {"$set": {
            "username": "admin",
            "password": password,
            "role": "admin"
        }},
        upsert=True
    )

    return "admin created"

# ===== RUN =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

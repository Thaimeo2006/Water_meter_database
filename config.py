import json

with open("password/token_for_ai_dev.txt", "r") as f:
    AI_TOKEN = f.read().strip()

with open("password/jwt_secret_key.txt", "rb") as f:
    JWT_SECRET_KEY = f.read()

with open("config.json", "r") as f:
    config = json.load(f)
    JWT_ALGORITHM =config["jwt_algorithm"]
    USER_SESSION_TOKEN_EXPIRE_DAYS = config["user_session_token_expire_days"]
    ADMIN_SESSION_TOKEN_EXPIRE_DAYS = config["admin_session_token_expire_days"]
    TIME_ZONE = config["time_zone"]
    DEFAULT_RADIUS_M = config["default_radius_m"]
    DEFAULT_LIMIT_NEARBY_METERS = config["default_limit_nearby_meters"]
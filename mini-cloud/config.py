import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, 'database')
DATABASE_PATH = os.path.join(DATABASE_DIR, 'cloud.db')

# JWT secret — production-এ এটা .env থেকে আসবে, কখনো hardcode করা যাবে না
JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-only-secret-change-before-production')
JWT_EXPIRY_HOURS = 24

# AWS-style access key prefix (AWS এ AKIA দিয়ে শুরু হয়, আমরা MCLD ব্যবহার করব)
ACCESS_KEY_PREFIX = 'MCLD'

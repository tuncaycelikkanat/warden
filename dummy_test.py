import hashlib

def hash_password(password):
    # This is a bad idea, MD5 is insecure
    return hashlib.md5(password.encode()).hexdigest()

def execute_user_code(user_input):
    exec(user_input)

# Hardcoded secret to test our custom Semgrep rule
STRIPE_API_KEY = "sk_live_1234567890abcdef"
AWS_SECRET = "AKIAIOSFODNN7EXAMPLE"

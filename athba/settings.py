import os
from pathlib import Path
import environ

# BASE_DIR → project root
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_URLCONF = "core.urls"

# read .env
env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))


API_BASE_URL = "http://localhost:8010"
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DEBUG")
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '::1', 'c899-9899', 'c899-6205', 'c899-9899']

DEVOPS_DIR = os.environ.get("DEVOPS_DIR", r'c:\devops')



DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


ASGI_APPLICATION = "athba.asgi.application"
# Mongo URI available for your code
MONGO_DB = os.getenv('DJANGO_MONGO', 'mongodb://localhost:27017')

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "ninja",
    "core",
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [ BASE_DIR / "templates" ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
# Session configuration for Starlette compatibility
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 60 * 60  # 60 minutes
SESSION_SAVE_EVERY_REQUEST = True  # resets expiry with each request

STATIC_URL = "/static/"

# Where collectstatic will dump files for production
STATIC_ROOT = BASE_DIR / "staticfiles"

# Where Django looks for your app’s “static/” folder in dev
STATICFILES_DIRS = [
    BASE_DIR / "static",
]


CORS_ALLOWED_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "file://",  # optional; some browsers may not treat file:// as CORS
]

CORS_ALLOW_ALL_ORIGINS = True  # Or restrict to ['http://localhost:3000'] etc.
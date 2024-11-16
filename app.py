import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.urandom(24)

# Initialize extensions
db.init_app(app)

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

with app.app_context():
    import models
    db.create_all()

# Import routes after db initialization
from bot_handlers import setup_bot
from subscription_manager import setup_subscription_checks

# Setup bot and webhook
bot = setup_bot()
setup_subscription_checks(scheduler)

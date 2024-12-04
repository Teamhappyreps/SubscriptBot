import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# Initialize Flask
app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.urandom(24)

# Initialize extensions
db = SQLAlchemy(model_class=Base)
migrate = Migrate()

db.init_app(app)
migrate.init_app(app, db)

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Import routes and setup after db initialization
from subscription_manager import setup_subscription_checks

# Setup subscription checks
setup_subscription_checks(scheduler)

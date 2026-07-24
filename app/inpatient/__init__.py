from flask import Blueprint

bp = Blueprint('inpatient_web_bp', __name__, template_folder='templates')

from app.inpatient import routes, models, services
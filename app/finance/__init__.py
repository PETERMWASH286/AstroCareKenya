from flask import Blueprint

finance_web_bp = Blueprint('finance_web_bp', __name__,
                              template_folder='templates',
    static_folder='static')

from . import routes, models

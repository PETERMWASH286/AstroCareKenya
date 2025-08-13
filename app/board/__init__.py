from flask import Blueprint

board_bp = Blueprint('board', __name__, template_folder='templates', # Specifies where templates for this blueprint are located
    static_folder='static',    # Optional: Specifies static folder if blueprint has its own
    url_prefix='/board')

from . import routes, models, schemas, services

import os

from .api import create_app
from .application import load_application
from .config import Settings


settings = Settings.from_environment()
application = load_application(os.environ.get("BLUEPRINT_APPLICATION", ""))
app = create_app(settings, application)

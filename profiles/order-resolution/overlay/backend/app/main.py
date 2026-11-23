from .composition import create_app
from .config import Settings
from .order_resolution.application import build_application


settings = Settings.from_environment()
app = create_app(settings, build_application())

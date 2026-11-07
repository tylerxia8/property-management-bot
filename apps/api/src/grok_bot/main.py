from grok_bot.api.app import create_app
from grok_bot.settings import get_settings

app = create_app(get_settings())

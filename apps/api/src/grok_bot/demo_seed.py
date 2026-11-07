"""Load the isolated fixture sample. Refuses every other database."""

import os

from grok_bot.seed import seed_demo

if __name__ == "__main__":
    seed_demo(
        os.environ["MIGRATION_DATABASE_URL"],
        os.environ.get("APP_ENV", "production"),
        os.environ["SESSION_SECRET"],
    )

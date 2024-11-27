from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import date
import os
import psycopg2

class ClassTrackerBot:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.database_url = os.environ.get('DATABASE_URL')
        self.setup_database()
        self.setup_handlers()

    def get_db_connection(self):
        return psycopg2.connect(self.database_url)

    def setup_database(self):
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS class_attendance (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username TEXT NOT NULL,
                        class_date DATE NOT NULL
                    )
                ''')
                conn.commit()

    def setup_handlers(self):
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(CommandHandler('today', self.record_today))

    async def start(self, update: Update, context: CallbackContext):
        await update.message.reply_text(
            "Commands:\n"
            "/today - Record today's class"
        )

    async def record_today(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        today = date.today()
        
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO class_attendance (user_id, username, class_date) VALUES (%s, %s, %s)',
                    (user_id, username, today)
                )
                conn.commit()
        
        await update.message.reply_text(f"Recorded class for today ({today})")

    def run(self):
        print("Bot starting...")
        self.app.run_polling()

if __name__ == '__main__':
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    bot = ClassTrackerBot(token)
    bot.run()
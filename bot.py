from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import date
import os
import psycopg2

class ClassTrackerBot:
    def __init__(self, token):
        self.app = Application.builder().token(token).drop_pending_updates().build()
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
        self.app.add_handler(CommandHandler('check', self.check_classes))

    async def start(self, update: Update, context: CallbackContext):
        await update.message.reply_text(
            "Commands:\n"
            "/today - Record today's class\n"
            "/check - See all recorded classes"
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

    async def check_classes(self, update: Update, context: CallbackContext):
        current_user_id = update.effective_user.id
        
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get current user's classes
                cur.execute('''
                    SELECT array_agg(class_date ORDER BY class_date) as dates
                    FROM class_attendance
                    WHERE user_id = %s
                ''', (current_user_id,))
                user_classes = cur.fetchone()
                
                # Get other users' classes
                cur.execute('''
                    SELECT username, array_agg(class_date ORDER BY class_date) as dates
                    FROM class_attendance
                    WHERE user_id != %s
                    GROUP BY username
                ''', (current_user_id,))
                other_classes = cur.fetchall()

        message = "Classes taken:\n\n"
        
        # Show current user's classes
        if user_classes and user_classes[0]:
            date_list = [d.strftime('%Y-%m-%d') for d in user_classes[0]]
            message += f"Your classes:\n{', '.join(date_list)}\n\n"
            
        # Show other users' classes
        if other_classes:
            message += "Others:\n"
            for username, dates in other_classes:
                date_list = [d.strftime('%Y-%m-%d') for d in dates]
                message += f"{username}: {', '.join(date_list)}\n"
        
        if not user_classes[0] and not other_classes:
            message = "No classes recorded"
            
        await update.message.reply_text(message)

    def run(self):
        print("Bot starting...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    bot = ClassTrackerBot(token)
    bot.run()


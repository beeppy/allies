
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import date, datetime
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
        self.app.add_handler(CommandHandler('record', self.record_specific_date))
        self.app.add_handler(CommandHandler('check', self.check_classes))
        self.app.add_handler(CommandHandler('remove', self.remove_date))

    async def record_specific_date(self, update: Update, context: CallbackContext):
        try:
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        'INSERT INTO class_attendance (user_id, username, class_date) VALUES (%s, %s, %s)',
                        (user_id, username, class_date)
                    )
                    conn.commit()
            
            await update.message.reply_text(f"Recorded class for {class_date}")
            
        except (ValueError, IndexError):
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /record 2024-11-27")


    async def remove_date(self, update: Update, context: CallbackContext):
        try:
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        'DELETE FROM class_attendance WHERE user_id = %s AND class_date = %s',
                        (user_id, class_date)
                    )
                    deleted_rows = cur.rowcount
                    conn.commit()
            
            if deleted_rows > 0:
                await update.message.reply_text(f"Removed class record for {class_date}")
            else:
                await update.message.reply_text(f"No class record found for {class_date}")
                
        except (ValueError, IndexError):
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /remove 2024-11-27")

    
    
    async def start(self, update: Update, context: CallbackContext):
        await update.message.reply_text(
            "Commands:\n"
            "/today - Record today's class\n"
            "/record YYYY-MM-DD - Record a class with date (YYYY-MM-DD)\n"
            "/remove YYYY-MM-DD - Remove a class with date (YYYY-MM-DD)\n"
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
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT username, array_agg(class_date ORDER BY class_date) as dates
                    FROM class_attendance
                    GROUP BY username
                ''')
                all_classes = cur.fetchall()

        if not all_classes:
            await update.message.reply_text("No classes recorded")
            return

        message = ""
        for username, dates in all_classes:
            message += f"\n{username}'s classes taken:\n"
            if dates:
                date_list = [d.strftime('%Y-%m-%d') for d in dates]
                message += '\n'.join(date_list) + '\n'

        await update.message.reply_text(message.strip())

    def run(self):
        print("Bot starting...")
        self.app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    bot = ClassTrackerBot(token)
    bot.run()

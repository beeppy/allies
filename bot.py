
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import date, datetime
import os
import psycopg2
from flask import Flask, request


class ClassTrackerBot:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.database_url = os.environ.get('DATABASE_URL')
        self.setup_database()
        self.setup_handlers()
        self.is_running = False
        self.flask_app = Flask(__name__)
        self.flask_app.route('/webhook', methods=['POST'])(self.webhook_handler)
        

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
        self.app.add_error_handler(self.error_handler)

    async def error_handler(self, update: Update, context: CallbackContext) -> None:
        print(f'Update {update} caused error {context.error}')

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
                    WITH stats AS (
                        SELECT COUNT(*) as total_classes,
                            username,
                            array_agg(class_date ORDER BY class_date) as dates,
                            COUNT(*) OVER (PARTITION BY username) as user_count
                        FROM class_attendance
                        GROUP BY username
                    )
                    SELECT total_classes, username, dates, user_count 
                    FROM stats
                    ORDER BY user_count DESC
                ''')
                results = cur.fetchall()
                
        if not results:
            await update.message.reply_text("No classes recorded")
            return

        total_classes = results[0][0]
        credits_left = 100 - total_classes
        message = f"Total classes taken: {total_classes}\nCredits left: {credits_left}\n"

        for _, username, dates, count in results:
            message += f"\n{username}'s classes taken: {count}\n"
            date_list = [d.strftime('%Y-%m-%d') for d in dates]
            message += '\n'.join(date_list) + '\n'

        await update.message.reply_text(message.strip())


    async def webhook_handler(self):
        if request.method == "POST":
            await self.app.update_queue.put(Update.de_json(request.get_json(), self.app.bot))
        return "OK"

    def run(self):
        if self.is_running:
            return
        try:
            self.is_running = True
            print("Bot starting with webhook...")
            webhook_url = os.environ.get('WEBHOOK_URL')
            self.app.bot.set_webhook(webhook_url)
            port = int(os.environ.get('PORT', 8080))
            self.flask_app.run(host='0.0.0.0', port=port)
        finally:
            self.is_running = False   

if __name__ == '__main__':
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    bot = ClassTrackerBot(token)
    bot.run()

#     def run(self):
#         if self.is_running:
#             return
#         try:
#             self.is_running = True
#             print("Bot starting...")
#             self.app.run_polling(drop_pending_updates=True)
#         finally:
#             self.is_running = False

# if __name__ == '__main__':
#     token = os.environ.get('TELEGRAM_BOT_TOKEN')
#     bot = ClassTrackerBot(token)
#     bot.run()

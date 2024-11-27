from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import date, datetime
import os
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
from flask import Flask, request
import asyncio

class DatabaseManager:
    def __init__(self, database_url, min_conn=1, max_conn=10):
        self.pool = SimpleConnectionPool(min_conn, max_conn, database_url)

    @contextmanager
    def get_db_connection(self):
        connection = self.pool.getconn()
        try:
            yield connection
        finally:
            connection.commit()
            self.pool.putconn(connection)

    @contextmanager
    def get_db_cursor(self):
        with self.get_db_connection() as connection:
            cursor = connection.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

class ClassTrackerBot:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.database_url = os.environ.get('DATABASE_URL')
        self.db = DatabaseManager(self.database_url)
        self.setup_database()
        self.setup_handlers()
        self.flask_app = Flask(__name__)
        self.flask_app.route('/webhook', methods=['POST'])(self.webhook_handler)

    def setup_database(self):
        with self.db.get_db_cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS class_attendance (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT NOT NULL,
                    class_date DATE NOT NULL
                )
            ''')

    def setup_handlers(self):
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(CommandHandler('today', self.record_today))
        self.app.add_handler(CommandHandler('record', self.record_specific_date))
        self.app.add_handler(CommandHandler('check', self.check_classes))
        self.app.add_handler(CommandHandler('remove', self.remove_date))
        self.app.add_error_handler(self.error_handler)

    async def error_handler(self, update: Update, context: CallbackContext) -> None:
        print(f'Update {update} caused error {context.error}')

    async def start(self, update: Update, context: CallbackContext):
        await update.message.reply_text(
            "Commands:\n"
            "/today - Record today's class\n"
            "/record YYYY-MM-DD - Record a class with date (YYYY-MM-DD)\n"
            "/remove YYYY-MM-DD - Remove a class with date (YYYY-MM-DD)\n"
            "/check - See all recorded classes"
        )

    async def record_today(self, update: Update, context: CallbackContext):
        try:
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            today = date.today()
            
            with self.db.get_db_cursor() as cur:
                cur.execute(
                    'INSERT INTO class_attendance (user_id, username, class_date) VALUES (%s, %s, %s)',
                    (user_id, username, today)
                )
            
            await update.message.reply_text(f"Recorded class for today ({today})")
        except Exception as e:
            await update.message.reply_text(f"Error recording today's class: {str(e)}")

    async def record_specific_date(self, update: Update, context: CallbackContext):
        try:
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            
            with self.db.get_db_cursor() as cur:
                cur.execute(
                    'INSERT INTO class_attendance (user_id, username, class_date) VALUES (%s, %s, %s)',
                    (user_id, username, class_date)
                )
            
            await update.message.reply_text(f"Recorded class for {class_date}")
        except (ValueError, IndexError):
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /record 2024-11-27")

    async def remove_date(self, update: Update, context: CallbackContext):
        try:
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            
            with self.db.get_db_cursor() as cur:
                cur.execute(
                    'DELETE FROM class_attendance WHERE user_id = %s AND class_date = %s',
                    (user_id, class_date)
                )
                deleted_rows = cur.rowcount
            
            if deleted_rows > 0:
                await update.message.reply_text(f"Removed class record for {class_date}")
            else:
                await update.message.reply_text(f"No class record found for {class_date}")
        except (ValueError, IndexError):
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /remove 2024-11-27")

    async def check_classes(self, update: Update, context: CallbackContext):
        try:
            with self.db.get_db_cursor() as cur:
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

            for _, username, dates, user_count in results:
                date_list = [d.strftime('%Y-%m-%d') for d in dates]
                count = len(date_list)
                message += f"\n{username}'s classes taken: {count}\n"
                message += '\n'.join(date_list) + '\n'

            await update.message.reply_text(message.strip())
        except Exception as e:
            await update.message.reply_text(f"Error checking classes: {str(e)}")

    async def webhook_handler(self):
        data = request.get_json()
        update = Update.de_json(data, self.app.bot)
        await self.app.process_update(update)
        return 'OK'

    async def initialize(self):
        """Initialize the bot and set up webhook"""
        await self.app.initialize()
        print("Setting up webhook...")
        webhook_url = os.environ.get('WEBHOOK_URL')
        await self.app.bot.set_webhook(webhook_url)
        return self.flask_app

def create_app():
    """Create and initialize the Flask app with the bot"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    
    bot = ClassTrackerBot(token)
    asyncio.run(bot.initialize())
    return bot.flask_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# from telegram import Update
# from telegram.ext import Application, CommandHandler, CallbackContext
# from datetime import date, datetime
# import os
# import psycopg2
# from flask import Flask, request
# import asyncio


# class ClassTrackerBot:
#     def __init__(self, token):
#         self.app = Application.builder().token(token).build()
#         self.database_url = os.environ.get('DATABASE_URL')
#         self.setup_database()
#         self.setup_handlers()
#         self.is_running = False
#         self.flask_app = Flask(__name__)
#         self.flask_app.route('/webhook', methods=['POST'])(self.webhook_handler)
        

#     def get_db_connection(self):
#         return psycopg2.connect(self.database_url)

#     def setup_database(self):
#         with self.get_db_connection() as conn:
#             with conn.cursor() as cur:
#                 cur.execute('''
#                     CREATE TABLE IF NOT EXISTS class_attendance (
#                         id SERIAL PRIMARY KEY,
#                         user_id BIGINT NOT NULL,
#                         username TEXT NOT NULL,
#                         class_date DATE NOT NULL
#                     )
#                 ''')
#                 conn.commit()
#         return

#     def setup_handlers(self):
#         self.app.add_handler(CommandHandler('start', self.start))
#         self.app.add_handler(CommandHandler('today', self.record_today))
#         self.app.add_handler(CommandHandler('record', self.record_specific_date))
#         self.app.add_handler(CommandHandler('check', self.check_classes))
#         self.app.add_handler(CommandHandler('remove', self.remove_date))
#         self.app.add_error_handler(self.error_handler)
#         return

#     async def error_handler(self, update: Update, context: CallbackContext) -> None:
#         print(f'Update {update} caused error {context.error}')
#         return

#     async def record_specific_date(self, update: Update, context: CallbackContext):
#         await update.message.reply_text(f"record_specific_date")
#         try:
#             input_date = ' '.join(context.args)
#             class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
#             user_id = update.effective_user.id
#             username = update.effective_user.username or update.effective_user.first_name
#             await update.message.reply_text(f"record_specific_date 2")
#             with self.get_db_connection() as conn:
#                 with conn.cursor() as cur:
#                     cur.execute(
#                         'INSERT INTO class_attendance (user_id, username, class_date) VALUES (%s, %s, %s)',
#                         (user_id, username, class_date)
#                     )
#                     conn.commit()
            
#             await update.message.reply_text(f"Recorded class for {class_date}")
#             return
#         except (ValueError, IndexError):
#             await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /record 2024-11-27")
#             return

#     async def remove_date(self, update: Update, context: CallbackContext):
#         await update.message.reply_text(f"remove_date")
#         try:
#             input_date = context.args[1]
#             class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
#             user_id = update.effective_user.id
#             await update.message.reply_text(f"remove_date 2")
#             with self.get_db_connection() as conn:
#                 with conn.cursor() as cur:
#                     cur.execute(
#                         'DELETE FROM class_attendance WHERE user_id = %s AND class_date = %s',
#                         (user_id, class_date)
#                     )
#                     deleted_rows = cur.rowcount
#                     await update.message.reply_text(f"remove_date 3")
#                     conn.commit()
#                     await update.message.reply_text(f"remove_date 4")
#                     print(deleted_rows)
            
#             if deleted_rows > 0:
#                 await update.message.reply_text(f"Removed class record for {class_date}")
#                 return
#             else:
#                 await update.message.reply_text(f"No class record found for {class_date}")
#                 return
#         except (ValueError, IndexError):
#             print("remove error")
#             await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /remove 2024-11-27")
#             return
    
    
#     async def start(self, update: Update, context: CallbackContext):
#         await update.message.reply_text(
#             "Commands:\n"
#             "/today - Record today's class\n"
#             "/record YYYY-MM-DD - Record a class with date (YYYY-MM-DD)\n"
#             "/remove YYYY-MM-DD - Remove a class with date (YYYY-MM-DD)\n"
#             "/check - See all recorded classes"
#         )
#         return

#     async def record_today(self, update: Update, context: CallbackContext):
#         await update.message.reply_text(f"record_today")
#         try:
#             user_id = update.effective_user.id
#             username = update.effective_user.username or update.effective_user.first_name
#             today = date.today()
#             await update.message.reply_text(f"record_today 2")
#             with self.get_db_connection() as conn:
#                 with conn.cursor() as cur:
#                     cur.execute(
#                         'INSERT INTO class_attendance (user_id, username, class_date) VALUES (%s, %s, %s)',
#                         (user_id, username, today)
#                     )
#                     await update.message.reply_text(f"record_today 3")
#                     conn.commit()
#                     await update.message.reply_text(f"record_today 4")
            
#             await update.message.reply_text(f"Recorded class for today ({today})")
#             return
#         except RuntimeError as e:
#             await update.message.reply_text(f"Error recording today's class: {e}")
#             return
#         except Exception as e:
#             await update.message.reply_text(f"Unexpected error: {e}")
#             return
            

#     async def check_classes(self, update: Update, context: CallbackContext):
#         await update.message.reply_text(f"check classes")
#         try:
#             with self.get_db_connection() as conn:
#                 with conn.cursor() as cur:
#                     cur.execute('''
#                         WITH stats AS (
#                             SELECT COUNT(*) as total_classes,
#                                 username,
#                                 array_agg(class_date ORDER BY class_date) as dates,
#                                 COUNT(*) OVER (PARTITION BY username) as user_count
#                             FROM class_attendance
#                             GROUP BY username
#                         )
#                         SELECT total_classes, username, dates, user_count 
#                         FROM stats
#                         ORDER BY user_count DESC
#                     ''')
#                     await update.message.reply_text(f"check_classes 2")
#                     results = cur.fetchall()
#                     await update.message.reply_text(f"check_classes 3")
#         except RuntimeError as e:
#             await update.message.reply_text(f"Error checking classes: {e}")
#             return
#         except Exception as e:
#             await update.message.reply_text(f"Unexpected error: {e}")
#             return

#         if not results:
#             await update.message.reply_text("No classes recorded")
#             return

#         total_classes = results[0][0]
#         credits_left = 100 - total_classes
#         message = f"Total classes taken: {total_classes}\nCredits left: {credits_left}\n"
#         await update.message.reply_text(f"check_classes 4")
#         for _, username, dates, user_count in results:
#             await update.message.reply_text(f"loop result")
#             date_list = [d.strftime('%Y-%m-%d') for d in dates]
#             count = len(date_list)
#             message += f"\n{username}'s classes taken: {count}\n"
#             message += '\n'.join(date_list) + '\n'

#         await update.message.reply_text(message.strip())
#         return
    
#     async def webhook_handler(self):
#         data = request.get_json()
#         update = Update.de_json(data, self.app.bot)
#         await self.app.process_update(update)
#         return 'OK'

#     async def run(self):
#         if self.is_running:
#             return
#         try:
#             self.is_running = True
#             await self.app.initialize()
#             print("Bot starting with webhook...")
#             webhook_url = os.environ.get('WEBHOOK_URL')
#             await self.app.bot.delete_webhook()
#             await self.app.bot.set_webhook(webhook_url)
#             return self.flask_app
#         finally:
#             self.is_running = False
#             return

# # Add this line outside the if block
# token = os.environ.get('TELEGRAM_BOT_TOKEN')
# bot = ClassTrackerBot(token)
# app = asyncio.run(bot.run())

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import date, datetime
import os
from contextlib import asynccontextmanager
from flask import Flask, request
import asyncio
import asyncpg

class DatabaseManager:
    def __init__(self, database_url):
        self.database_url = database_url
        self.pool = None

    async def initialize(self):
        self.pool = await asyncpg.create_pool(self.database_url)

    async def setup_database(self):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS class_attendance (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT NOT NULL,
                    class_date DATE NOT NULL
                )
            ''')

    @asynccontextmanager
    async def get_db_cursor(self):
        async with self.pool.acquire() as connection:
            try:
                yield connection
            finally:
                pass

class ClassTrackerBot:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.database_url = os.environ.get('DATABASE_URL')
        self.db = DatabaseManager(self.database_url)
        self.flask_app = Flask(__name__)
        self.flask_app.route('/webhook', methods=['POST'])(self.webhook_handler)

    async def setup_handlers(self):
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(CommandHandler('today', self.record_today))
        self.app.add_handler(CommandHandler('record', self.record_specific_date))
        self.app.add_handler(CommandHandler('check', self.check_classes))
        self.app.add_handler(CommandHandler('remove', self.remove_date))
        self.app.add_error_handler(self.error_handler)

    async def error_handler(self, update: Update, context: CallbackContext) -> None:
        await update.message.reply_text(f'Update {update} caused error {context.error}')

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
            
            async with self.db.get_db_cursor() as conn:
                await conn.execute('''
                    INSERT INTO class_attendance (user_id, username, class_date) 
                    VALUES ($1, $2, $3)
                ''', user_id, username, today)
            
            await update.message.reply_text(f"Recorded class for today ({today})")
        except Exception as e:
            await update.message.reply_text(f"Error recording today's class: {str(e)}")

    async def record_specific_date(self, update: Update, context: CallbackContext):
        try:
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            
            async with self.db.get_db_cursor() as conn:
                await conn.execute('''
                    INSERT INTO class_attendance (user_id, username, class_date) 
                    VALUES ($1, $2, $3)
                ''', user_id, username, class_date)
            
            await update.message.reply_text(f"Recorded class for {class_date}")
        except (ValueError, IndexError):
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /record 2024-11-27")

    async def remove_date(self, update: Update, context: CallbackContext):
        try:
            await update.message.reply_text("Starting remove_date operation...")
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            await update.message.reply_text(f"Attempting to remove date {class_date} for user {user_id}")
            
            async with self.db.get_db_cursor() as conn:
                result = await conn.execute('''
                    DELETE FROM class_attendance 
                    WHERE user_id = $1 AND class_date = $2
                ''', user_id, class_date)
                deleted_rows = int(result.split()[1])
                await update.message.reply_text(f"Deleted {deleted_rows} rows")
            
            await asyncio.sleep(1)  # Add small delay to ensure DB operation completes
            
            if deleted_rows > 0:
                await update.message.reply_text(f"Removed class record for {class_date}")
            else:
                await update.message.reply_text(f"No class record found for {class_date}")
        except (ValueError, IndexError) as e:
            print(f"Input format error: {str(e)}")
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /remove 2024-11-27")

    async def check_classes(self, update: Update, context: CallbackContext):
        try:
            async with self.db.get_db_cursor() as conn:
                results = await conn.fetch('''
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

            if not results:
                await update.message.reply_text("No classes recorded")
                return

            total_classes = results[0]['total_classes']
            credits_left = 100 - total_classes
            message = f"Total classes taken: {total_classes}\nCredits left: {credits_left}\n"

            for row in results:
                date_list = [d.strftime('%Y-%m-%d') for d in row['dates']]
                count = len(date_list)
                message += f"\n{row['username']}'s classes taken: {count}\n"
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
        await self.db.initialize()  # Initialize DB pool
        await self.db.setup_database()  # Setup tables
        await self.setup_handlers()  # Setup command handlers
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


#-- works but response only once every 2 messages
# from telegram import Update
# from telegram.ext import Application, CommandHandler, CallbackContext
# from datetime import date, datetime
# import os
# import psycopg2
# from psycopg2.pool import SimpleConnectionPool
# from contextlib import contextmanager
# from flask import Flask, request
# import asyncio

# class DatabaseManager:
#     def __init__(self, database_url, min_conn=1, max_conn=10):
#         self.pool = SimpleConnectionPool(min_conn, max_conn, database_url)

#     @contextmanager
#     def get_db_connection(self):
#         connection = self.pool.getconn()
#         try:
#             yield connection
#         finally:
#             connection.commit()
#             self.pool.putconn(connection)

#     @contextmanager
#     def get_db_cursor(self):
#         with self.get_db_connection() as connection:
#             cursor = connection.cursor()
#             try:
#                 yield cursor
#             finally:
#                 cursor.close()

# class ClassTrackerBot:
#     def __init__(self, token):
#         self.app = Application.builder().token(token).build()
#         self.database_url = os.environ.get('DATABASE_URL')
#         self.db = DatabaseManager(self.database_url)
#         self.setup_database()
#         self.setup_handlers()
#         self.flask_app = Flask(__name__)
#         self.flask_app.route('/webhook', methods=['POST'])(self.webhook_handler)

#     def setup_database(self):
#         with self.db.get_db_cursor() as cur:
#             cur.execute('''
#                 CREATE TABLE IF NOT EXISTS class_attendance (
#                     id SERIAL PRIMARY KEY,
#                     user_id BIGINT NOT NULL,
#                     username TEXT NOT NULL,
#                     class_date DATE NOT NULL
#                 )
#             ''')

#     def setup_handlers(self):
#         self.app.add_handler(CommandHandler('start', self.start))
#         self.app.add_handler(CommandHandler('today', self.record_today))
#         self.app.add_handler(CommandHandler('record', self.record_specific_date))
#         self.app.add_handler(CommandHandler('check', self.check_classes))
#         self.app.add_handler(CommandHandler('remove', self.remove_date))
#         self.app.add_error_handler(self.error_handler)

#     async def error_handler(self, update: Update, context: CallbackContext) -> None:
#         print(f'Update {update} caused error {context.error}')

#     async def start(self, update: Update, context: CallbackContext):
#         await update.message.reply_text(
#             "Commands:\n"
#             "/today - Record today's class\n"
#             "/record YYYY-MM-DD - Record a class with date (YYYY-MM-DD)\n"
#             "/remove YYYY-MM-DD - Remove a class with date (YYYY-MM-DD)\n"
#             "/check - See all recorded classes"
#         )

#     async def record_today(self, update: Update, context: CallbackContext):
#         try:
#             user_id = update.effective_user.id
#             username = update.effective_user.username
#             today = date.today()
            
#             with self.db.get_db_cursor() as cur:
#                 cur.execute(
#                     'INSERT INTO class_attendance (user_id, username, class_date) VALUES (%s, %s, %s)',
#                     (user_id, username, today)
#                 )
            
#             await update.message.reply_text(f"Recorded class for today ({today})")
#         except Exception as e:
#             await update.message.reply_text(f"Error recording today's class: {str(e)}")

#     async def record_specific_date(self, update: Update, context: CallbackContext):
#         try:
#             input_date = ' '.join(context.args)
#             class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
#             user_id = update.effective_user.id
#             username = update.effective_user.username
            
#             with self.db.get_db_cursor() as cur:
#                 cur.execute(
#                     'INSERT INTO class_attendance (user_id, username, class_date) VALUES (%s, %s, %s)',
#                     (user_id, username, class_date)
#                 )
            
#             await update.message.reply_text(f"Recorded class for {class_date}")
#         except (ValueError, IndexError):
#             await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /record 2024-11-27")

#     async def remove_date(self, update: Update, context: CallbackContext):
#         try:
#             input_date = ' '.join(context.args)
#             class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
#             user_id = update.effective_user.id
            
#             with self.db.get_db_cursor() as cur:
#                 cur.execute(
#                     'DELETE FROM class_attendance WHERE user_id = %s AND class_date = %s',
#                     (user_id, class_date)
#                 )
#                 deleted_rows = cur.rowcount
            
#             if deleted_rows > 0:
#                 await update.message.reply_text(f"Removed class record for {class_date}")
#             else:
#                 await update.message.reply_text(f"No class record found for {class_date}")
#         except (ValueError, IndexError):
#             await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /remove 2024-11-27")

#     async def check_classes(self, update: Update, context: CallbackContext):
#         try:
#             with self.db.get_db_cursor() as cur:
#                 cur.execute('''
#                     WITH stats AS (
#                         SELECT COUNT(*) as total_classes,
#                             username,
#                             array_agg(class_date ORDER BY class_date) as dates,
#                             COUNT(*) OVER (PARTITION BY username) as user_count
#                         FROM class_attendance
#                         GROUP BY username
#                     )
#                     SELECT total_classes, username, dates, user_count 
#                     FROM stats
#                     ORDER BY user_count DESC
#                 ''')
#                 results = cur.fetchall()

#             if not results:
#                 await update.message.reply_text("No classes recorded")
#                 return

#             total_classes = results[0][0]
#             credits_left = 100 - total_classes
#             message = f"Total classes taken: {total_classes}\nCredits left: {credits_left}\n"

#             for _, username, dates, user_count in results:
#                 date_list = [d.strftime('%Y-%m-%d') for d in dates]
#                 count = len(date_list)
#                 message += f"\n{username}'s classes taken: {count}\n"
#                 message += '\n'.join(date_list) + '\n'

#             await update.message.reply_text(message.strip())
#         except Exception as e:
#             await update.message.reply_text(f"Error checking classes: {str(e)}")

#     async def webhook_handler(self):
#         data = request.get_json()
#         update = Update.de_json(data, self.app.bot)
#         await self.app.process_update(update)
#         return 'OK'

#     async def initialize(self):
#         """Initialize the bot and set up webhook"""
#         await self.app.initialize()
#         print("Setting up webhook...")
#         webhook_url = os.environ.get('WEBHOOK_URL')
#         await self.app.bot.set_webhook(webhook_url)
#         return self.flask_app

# def create_app():
#     """Create and initialize the Flask app with the bot"""
#     token = os.environ.get('TELEGRAM_BOT_TOKEN')
#     if not token:
#         raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    
#     bot = ClassTrackerBot(token)
#     asyncio.run(bot.initialize())
#     return bot.flask_app

# app = create_app()

# if __name__ == '__main__':
#     port = int(os.environ.get('PORT', 5000))
#     app.run(host='0.0.0.0', port=port)


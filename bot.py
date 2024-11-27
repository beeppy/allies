from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import date, datetime
import os
from contextlib import asynccontextmanager
from flask import Flask, request
import asyncio
import asyncpg
from asgiref.sync import async_to_sync, sync_to_async

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
        database_url = os.environ.get('DATABASE_URL')
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        self.database_url = database_url
        self.db = DatabaseManager(self.database_url)
        self.flask_app = Flask(__name__)
        self.register_webhook_handler()
        self._loop = None
        
    def get_loop(self):
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def register_webhook_handler(self):
        self.flask_app.route('/webhook', methods=['POST'])(self.webhook_handler)

    def webhook_handler(self):
        if not request.is_json:
            return 'Invalid request', 400
        
        data = request.get_json()
        update = Update.de_json(data, self.app.bot)
        
        loop = self.get_loop()
        async_to_sync(self.process_update)(update)
        return 'OK'

    async def process_update(self, update: Update):
        await self.app.process_update(update)

    async def setup_handlers(self):
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(CommandHandler('today', self.record_today))
        self.app.add_handler(CommandHandler('record', self.record_specific_date))
        self.app.add_handler(CommandHandler('check', self.check_classes))
        self.app.add_handler(CommandHandler('remove', self.remove_date))
        self.app.add_error_handler(self.error_handler)

    async def error_handler(self, update: Update, context: CallbackContext) -> None:
        error_msg = f'Update {update} caused error {context.error}'
        print(error_msg)
        await update.message.reply_text(f"Error occurred: {error_msg}")

    async def start(self, update: Update, context: CallbackContext):
        await update.message.reply_text("Starting command received...")
        await update.message.reply_text(
            "Commands:\n"
            "/today - Record today's class\n"
            "/record YYYY-MM-DD - Record a class with date (YYYY-MM-DD)\n"
            "/remove YYYY-MM-DD - Remove a class with date (YYYY-MM-DD)\n"
            "/check - See all recorded classes"
        )

    async def record_today(self, update: Update, context: CallbackContext):
        try:
            await update.message.reply_text("Processing today's record...")
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            today = date.today()
            
            await update.message.reply_text("Connecting to database...")
            async with self.db.get_db_cursor() as conn:
                await update.message.reply_text("Executing insert query...")
                await conn.execute('''
                    INSERT INTO class_attendance (user_id, username, class_date) 
                    VALUES ($1, $2, $3)
                ''', user_id, username, today)
                await update.message.reply_text("Database insert completed")
            
            await update.message.reply_text(f"Successfully recorded class for today ({today})")
        except Exception as e:
            error_msg = f"Error recording today's class: {str(e)}"
            print(error_msg)
            await update.message.reply_text(error_msg)

    async def record_specific_date(self, update: Update, context: CallbackContext):
        try:
            await update.message.reply_text("Processing specific date record...")
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            
            await update.message.reply_text("Connecting to database...")
            async with self.db.get_db_cursor() as conn:
                await update.message.reply_text("Executing insert query...")
                await conn.execute('''
                    INSERT INTO class_attendance (user_id, username, class_date) 
                    VALUES ($1, $2, $3)
                ''', user_id, username, class_date)
                await update.message.reply_text("Database insert completed")
            
            await update.message.reply_text(f"Successfully recorded class for {class_date}")
        except (ValueError, IndexError):
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /record 2024-11-27")
        except Exception as e:
            error_msg = f"Error recording specific date: {str(e)}"
            print(error_msg)
            await update.message.reply_text(error_msg)

    async def remove_date(self, update: Update, context: CallbackContext):
        try:
            await update.message.reply_text("Starting remove date operation...")
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            await update.message.reply_text(f"Attempting to remove date {class_date} for user {user_id}")
            
            await update.message.reply_text("Connecting to database...")
            async with self.db.get_db_cursor() as conn:
                await update.message.reply_text("Executing delete query...")
                result = await conn.execute('''
                    DELETE FROM class_attendance 
                    WHERE user_id = $1 AND class_date = $2
                ''', user_id, class_date)
                deleted_rows = int(result.split()[1])
                await update.message.reply_text(f"Delete query completed. Rows affected: {deleted_rows}")
            
            if deleted_rows > 0:
                await update.message.reply_text(f"Successfully removed class record for {class_date}")
            else:
                await update.message.reply_text(f"No class record found for {class_date}")
        except (ValueError, IndexError) as e:
            error_msg = f"Date format error: {str(e)}"
            print(error_msg)
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /remove 2024-11-27")
        except Exception as e:
            error_msg = f"Error removing date: {str(e)}"
            print(error_msg)
            await update.message.reply_text(error_msg)

    async def check_classes(self, update: Update, context: CallbackContext):
        try:
            await update.message.reply_text("Starting class check...")
            await update.message.reply_text("Connecting to database...")
            
            async with self.db.get_db_cursor() as conn:
                await update.message.reply_text("Executing select query...")
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
                await update.message.reply_text("Select query completed")

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

            await update.message.reply_text("Preparing final results...")
            await update.message.reply_text(message.strip())
        except Exception as e:
            error_msg = f"Error checking classes: {str(e)}"
            print(error_msg)
            await update.message.reply_text(error_msg)

    async def initialize(self):
        await update.message.reply_text("Initializing bot...")
        await self.app.initialize()
        await update.message.reply_text("Initializing database...")
        await self.db.initialize()
        await self.db.setup_database()
        await update.message.reply_text("Setting up command handlers...")
        await self.setup_handlers()
        print("Setting up webhook...")
        webhook_url = os.environ.get('WEBHOOK_URL')
        await self.app.bot.set_webhook(webhook_url)
        return self.flask_app

    def run(self):
        loop = self.get_loop()
        async_to_sync(self.initialize)()
        return self.flask_app

def create_app():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    
    bot = ClassTrackerBot(token)
    return bot.run()

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from datetime import date, datetime
import os
from contextlib import asynccontextmanager
from flask import Flask, request
import asyncio
import asyncpg
from asgiref.sync import async_to_sync, sync_to_async
import logging

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, database_url):
        self.database_url = database_url
        self.pool = None

    async def initialize(self):
        try:
            logger.info("Initializing database pool...")
            self.pool = await asyncpg.create_pool(self.database_url)
            logger.info("Database pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

    async def setup_database(self):
        try:
            logger.info("Setting up database tables...")
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS class_attendance (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username TEXT NOT NULL,
                        class_date DATE NOT NULL
                    )
                ''')
            logger.info("Database tables setup completed")
        except Exception as e:
            logger.error(f"Failed to setup database tables: {e}")
            raise

    @asynccontextmanager
    async def get_db_cursor(self):
        async with self.pool.acquire() as connection:
            try:
                yield connection
            finally:
                pass

class ClassTrackerBot:
    def __init__(self, token):
        try:
            logger.info("Initializing ClassTrackerBot...")
            self.app = Application.builder().token(token).build()
            database_url = os.environ.get('DATABASE_URL')
            if not database_url:
                raise ValueError("DATABASE_URL environment variable is not set")
            
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            
            self.database_url = database_url
            self.db = DatabaseManager(self.database_url)
            self.flask_app = Flask(__name__)
            self.register_webhook_handler()
            logger.info("ClassTrackerBot initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ClassTrackerBot: {e}")
            raise

    def register_webhook_handler(self):
        try:
            logger.info("Registering webhook handler...")
            self.flask_app.route('/webhook', methods=['POST'])(self.webhook_handler)
            logger.info("Webhook handler registered successfully")
        except Exception as e:
            logger.error(f"Failed to register webhook handler: {e}")
            raise

    def webhook_handler(self):
        try:
            if not request.is_json:
                logger.warning("Received non-JSON request")
                return 'Invalid request', 400
            
            data = request.get_json()
            update = Update.de_json(data, self.app.bot)
            async_to_sync(self.app.process_update)(update)
            return 'OK'
        except Exception as e:
            logger.error(f"Error in webhook handler: {e}")
            return 'Error processing webhook', 500

    async def setup_handlers(self):
        try:
            logger.info("Setting up command handlers...")
            self.app.add_handler(CommandHandler('start', self.start))
            self.app.add_handler(CommandHandler('today', self.record_today))
            self.app.add_handler(CommandHandler('record', self.record_specific_date))
            self.app.add_handler(CommandHandler('check', self.check_classes))
            self.app.add_handler(CommandHandler('remove', self.remove_date))
            self.app.add_error_handler(self.error_handler)
            logger.info("Command handlers setup completed")
        except Exception as e:
            logger.error(f"Failed to setup command handlers: {e}")
            raise

    # [Your existing command handlers remain the same]

    async def initialize(self):
        """Initialize the bot and set up webhook"""
        try:
            logger.info("Starting bot initialization...")
            
            # Initialize the application
            logger.info("Initializing Telegram application...")
            await self.app.initialize()
            logger.info("Telegram application initialized")

            # Initialize database
            logger.info("Initializing database...")
            await self.db.initialize()
            await self.db.setup_database()
            logger.info("Database initialization completed")

            # Setup command handlers
            logger.info("Setting up command handlers...")
            await self.setup_handlers()
            logger.info("Command handlers setup completed")

            # Setup webhook
            logger.info("Setting up webhook...")
            webhook_url = os.environ.get('WEBHOOK_URL')
            if not webhook_url:
                raise ValueError("WEBHOOK_URL environment variable is not set")
            
            await self.app.bot.set_webhook(webhook_url)
            logger.info("Webhook setup completed")
            
            logger.info("Bot initialization completed successfully")
            return self.flask_app
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise




    async def error_handler(self, update: Update, context: CallbackContext) -> None:
        logger.error(f'Update {update} caused error {context.error}')

    async def start(self, update: Update, context: CallbackContext):
        logger.info("Start command received")
        await update.message.reply_text(
            "Commands:\n"
            "/today - Record today's class\n"
            "/record YYYY-MM-DD - Record a class with date (YYYY-MM-DD)\n"
            "/remove YYYY-MM-DD - Remove a class with date (YYYY-MM-DD)\n"
            "/check - See all recorded classes"
        )

    async def record_today(self, update: Update, context: CallbackContext):
        try:
            logger.info("Recording today's class")
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            today = date.today()
            
            async with self.db.get_db_cursor() as conn:
                await conn.execute('''
                    INSERT INTO class_attendance (user_id, username, class_date) 
                    VALUES ($1, $2, $3)
                ''', user_id, username, today)
            
            await update.message.reply_text(f"Recorded class for today ({today})")
            logger.info(f"Successfully recorded class for user {username}")
        except Exception as e:
            logger.error(f"Error recording today's class: {e}")
            await update.message.reply_text(f"Error recording today's class: {str(e)}")

    async def record_specific_date(self, update: Update, context: CallbackContext):
        try:
            logger.info("Recording specific date")
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
            logger.info(f"Successfully recorded class for {username} on {class_date}")
        except (ValueError, IndexError):
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /record 2024-11-27")
        except Exception as e:
            logger.error(f"Error recording specific date: {e}")
            await update.message.reply_text(f"Error recording class: {str(e)}")

    async def remove_date(self, update: Update, context: CallbackContext):
        try:
            logger.info("Removing date")
            input_date = ' '.join(context.args)
            class_date = datetime.strptime(input_date, '%Y-%m-%d').date()
            
            user_id = update.effective_user.id
            
            async with self.db.get_db_cursor() as conn:
                result = await conn.execute('''
                    DELETE FROM class_attendance 
                    WHERE user_id = $1 AND class_date = $2
                ''', user_id, class_date)
                deleted_rows = int(result.split()[1])
            
            if deleted_rows > 0:
                await update.message.reply_text(f"Removed class record for {class_date}")
                logger.info(f"Successfully removed class record for {class_date}")
            else:
                await update.message.reply_text(f"No class record found for {class_date}")
                logger.info(f"No class record found for {class_date}")
        except (ValueError, IndexError):
            await update.message.reply_text("Please provide a date in YYYY-MM-DD format\nExample: /remove 2024-11-27")
        except Exception as e:
            logger.error(f"Error removing date: {e}")
            await update.message.reply_text(f"Error removing class: {str(e)}")

    async def check_classes(self, update: Update, context: CallbackContext):
        try:
            logger.info("Checking classes")
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
            logger.info("Successfully checked classes")
        except Exception as e:
            logger.error(f"Error checking classes: {e}")
            await update.message.reply_text(f"Error checking classes: {str(e)}")

def create_app():
        """Create and initialize the Flask app with the bot"""
        try:
            logger.info("Starting application creation...")
            
            # Verify environment variables
            token = os.environ.get('TELEGRAM_BOT_TOKEN')
            if not token:
                raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

            # Create and initialize bot
            bot = ClassTrackerBot(token)
            
            # Setup event loop
            logger.info("Setting up event loop...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Initialize bot
            logger.info("Initializing bot...")
            flask_app = loop.run_until_complete(bot.initialize())
            
            logger.info("Application creation completed successfully")
            return flask_app
        except Exception as e:
            logger.error(f"Failed to create application: {e}")
            raise
        
# Create the Flask app with error handling
try:
    logger.info("Starting application...")
    app = create_app()
    logger.info("Application started successfully")
except Exception as e:
    logger.error(f"Failed to start application: {e}")
    raise

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
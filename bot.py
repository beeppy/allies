from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext

class SimpleBot:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.setup_handlers()

    def setup_handlers(self):
        # Add command handlers
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(CommandHandler('hello', self.hello))
        self.app.add_handler(CommandHandler('help', self.help))

    async def start(self, update: Update, context: CallbackContext):
        await update.message.reply_text(
            "👋 Welcome! I'm your test bot.\n\n"
            "Available commands:\n"
            "/hello - Say hello\n"
            "/help - Show this help message"
        )

    async def hello(self, update: Update, context: CallbackContext):
        user_name = update.effective_user.first_name
        await update.message.reply_text(f"Hello {user_name}! 👋")

    async def help(self, update: Update, context: CallbackContext):
        await update.message.reply_text(
            "Here's what I can do:\n"
            "/hello - I'll say hello to you\n"
            "/help - Show this help message"
        )

    def run(self):
        print("Bot is starting...")
        self.app.run_polling()


if __name__ == '__main__':
    import os
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    bot = SimpleBot(token)
    bot.run()
    
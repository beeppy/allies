# Ally Pilates Class Tracker Bot

A Telegram bot for tracking shared Pilates class credits at Ally Pilates Studio. Built to solve the challenge of managing shared class packages between multiple users.

## Features

- Record classes taken (today or specific dates)
- Remove incorrectly recorded classes
- Check remaining credits
- View class history for all users sharing the package
- Track total classes taken and credits left from 100-class package

## Commands

- `/today` - Record today's class
- `/record YYYY-MM-DD` - Record a class for a specific date
- `/remove YYYY-MM-DD` - Remove a recorded class
- `/check` - View all recorded classes and remaining credits
- `/start` - Show available commands

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather)
2. Get your bot token
3. Set up environment variables:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
DATABASE_URL=your_postgres_database_url
```
4. Install dependencies:
```bash
pip install python-telegram-bot psycopg2-binary
```
5. Run the bot:
```bash
python bot.py
```

## Group Chat Usage

1. Add bot to your Telegram group
2. Make bot an admin
3. Use commands with @BotName (e.g., `/today@YourBotName`)

## Database Schema

```sql
CREATE TABLE class_attendance (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT NOT NULL,
    class_date DATE NOT NULL
)
```

## Development

Built with:
- python-telegram-bot
- PostgreSQL
- psycopg2

## License

MIT License

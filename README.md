# Life-Balance-Telegram-Bot

This project is a personal finance tracker built with a Telegram bot and the Google Sheets API. Users can add income and expenses under custom categories, and the bot sends the data to their associated spreadsheets.

To deploy the project, run `main.py` and provide the Google service-account credentials, spreadsheet links, and Telegram token configuration files.

Users start with preconfigured categories and can add or remove their own categories through Telegram.

## Recurring expenses

- `/add_recurring_expense`: creates a personal or shared monthly expense, starting next month.
- `/delete_recurring_expense`: deletes a recurring expense. Either shared-plan member can delete shared entries.

The bot stores recurring definitions and their per-month processing state in `recurringExpenses.json`.

Recurring expenses are added on the first day of each month at 10:00 in the `Europe/Rome` timezone. If the bot was offline, it catches up when it starts again.

Set `BOT_DATA_DIRECTORY` to place runtime JSON files in a persistent directory. The included Docker build script mounts the `life-balance-data` volume at `/data`, so recurring expenses survive container rebuilds.

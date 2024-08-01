# Life-Balance-Telegram-Bot

<br /><br />This project aims to build a personal finance tracker using Google SpreadSheet API and telegram bot.
By using the telegram bot we can add incomes and expenses under user custom categories. Then this data will be send to the associated google spreadsheet to manage all the calculations.

<br />To deploy the project you just need to run the telegram bot server (main.py file), and add the keys to the Google Tecnical Account (to write on the sheet) and the link to the sheet itself.<br /><br />

A new user start with a default set of pre-initialized categories; then the user, through the telegram bot interface, is able to add/remove his own categories.

In this case, for the pourpose of the use-case, i'm storing all the data in a spreadsheet sheet using it as a DB to Analyze the data as needed. Evolution to store the date in a relational/non-relational DB can be made to analyze the data with BI tools for example.

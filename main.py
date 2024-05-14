import logging
from datetime import date
import json
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from telegram import Bot
from datetime import date
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    CallbackContext,
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def initializeSpreadsheetAPI(spreadsheetLink):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    #SERVICE_ACCOUNT_FILE = '/home/pi/Desktop/projects/Life-Balance-Telegram-Bot/spreadsheetKeys.json'
    SERVICE_ACCOUNT_FILE = './spreadsheetKeys.json'
    credentials = None
    credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    SAMPLE_SPREADSHEET_ID = spreadsheetLink
    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()

    return sheet, SAMPLE_SPREADSHEET_ID




directory = "/home/pi/Desktop/projects/Life-Balance-Telegram-Bot/"

"""Retriving users categories"""
try:
    #f = open(directory + "spreadsheetLinks.json")
    f = open("./userCategories.json")
    data = json.load(f)
    user_categories = data
except IndexError as e:
    print(e)

types = ['Income', 'Expense']
ids_mapping = {"federico": "224331200", "carolina": "6464119475"}

EXPENSE_CATEGORY, EXPENSE_DESC, EXPENSE_AMOUNT = range(3)
INCOME_CATEGORY, INCOME_DESC, INCOME_AMOUNT = range(3)
CATEGORY_NAME, CATEGORY_TYPE = range(2)

sheet = None
SAMPLE_SPREADSHEET_ID = None

selected_expense_amount = 0
selected_expense_category = ""
selected_income_amount = 0
selected_income_category = ""

sheetFederico, SAMPLE_SPREADSHEET_ID_FEDERICO = "", ""
sheetCarolina, SAMPLE_SPREADSHEET_ID_CAROLINA = "", ""

try:
    #f = open(directory + "spreadsheetLinks.json")
    f = open("./spreadsheetLinks.json")
    data = json.load(f)
    sheetFederico, SAMPLE_SPREADSHEET_ID_FEDERICO = initializeSpreadsheetAPI(data["life_balance_federico"])
    sheetCarolina, SAMPLE_SPREADSHEET_ID_CAROLINA = initializeSpreadsheetAPI(data["life_balance_carolina"])
    
except IndexError as e:
    print(e)

#Commands section
async def start(update: Update, context: CallbackContext):

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Welcome, i am glad you are managing your finance, keep it up!!!'
    )
    print(update.effective_chat.id)

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        'Current action canceled. \n\nChoose your next action... \n\n', reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def add_expense(update: Update, context: CallbackContext) -> int:
    global current_user
    current_user = str(update.message.from_user.id)
    #i need a dynamic reply keyboard to fit to screen
    reply_keyboard = [user_categories[current_user]["Expense"][:4], user_categories[current_user]["Expense"][4:8], user_categories[current_user]["Expense"][8:]]
    await update.message.reply_text(
        "Select the expense category..., \n\n/cancel to UNDO", 
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, one_time_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return EXPENSE_CATEGORY

async def add_expense_1(update: Update, context: CallbackContext) -> int:

    global selected_expense_category
    selected_expense_category = update.message.text
    await update.message.reply_text("Type the amount spent, \n\n/cancel to UNDO") 

    return EXPENSE_AMOUNT

async def add_expense_2(update: Update, context: CallbackContext) -> int:

    global selected_expense_amount 
    selected_expense_amount = update.message.text
    await update.message.reply_text("Type a description, \n\n/cancel to UNDO")

    return EXPENSE_DESC

async def add_expense_3(update: Update, context: CallbackContext) -> int:
    current_year = str(date.today().year)
    current_date = str(date.today().strftime("%d/%m/%Y"))
    current_month = str(date.today().strftime("%b"))
    global selected_expense_desc 
    selected_expense_desc = update.message.text

    if (ids_mapping["federico"] == str(update.message.from_user.id)):
        sheet, SAMPLE_SPREADSHEET_ID = sheetFederico, SAMPLE_SPREADSHEET_ID_FEDERICO
    else:
        sheet, SAMPLE_SPREADSHEET_ID = sheetCarolina, SAMPLE_SPREADSHEET_ID_CAROLINA
    
    try:

        sheet.values().append(spreadsheetId=SAMPLE_SPREADSHEET_ID, 
            range= "DB!A1" , valueInputOption="USER_ENTERED", body={"values":[['e', selected_expense_category, current_date, selected_expense_amount, selected_expense_desc, current_month]]}).execute()

        #get the total spent in the current month
        total_monthly_expense = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                            range= "NetWorth"+ current_year + "!" + chr(date.today().month + 66) + "12").execute()
    
    except IndexError as e:
        await update.message.reply_text(e)
        return ConversationHandler.END

    await update.message.reply_text(selected_expense_category + " Expense Updated!\n\nYour total monthly expense is: " + str(total_monthly_expense["values"][0][0]) + "💸 💸")

    return ConversationHandler.END

async def add_income(update: Update, context: CallbackContext) -> int:
    global current_user
    current_user = str(update.message.from_user.id)
    reply_keyboard = [user_categories[current_user]["Income"]]

    await update.message.reply_text(
        "Select the income category... \n\n/cancel to UNDO", 
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return INCOME_CATEGORY

async def add_income_1(update: Update, context: CallbackContext) -> int:

    global selected_income_category
    selected_income_category = update.message.text
    await update.message.reply_text("Type the amount earned, \n\n/cancel to UNDO")

    return INCOME_AMOUNT

async def add_income_2(update: Update, context: CallbackContext) -> int:

    global selected_income_amount
    selected_income_amount = update.message.text
    await update.message.reply_text("Type a description, \n\n/cancel to UNDO")

    return INCOME_DESC

async def add_income_3(update: Update, context: CallbackContext) -> int:
    current_year = str(date.today().year)
    current_date = str(date.today().strftime("%d/%m/%Y"))
    current_month = str(date.today().strftime("%b"))
    global selected_income_desc 
    selected_income_desc = update.message.text

    if (ids_mapping["federico"] == str(update.message.from_user.id)):
        sheet, SAMPLE_SPREADSHEET_ID = sheetFederico, SAMPLE_SPREADSHEET_ID_FEDERICO
    else:
        sheet, SAMPLE_SPREADSHEET_ID = sheetCarolina, SAMPLE_SPREADSHEET_ID_CAROLINA
    
    try:

        sheet.values().append(spreadsheetId=SAMPLE_SPREADSHEET_ID, 
            range= "DB!A1" , valueInputOption="USER_ENTERED", body={"values":[['i', selected_income_category, current_date, selected_income_amount, selected_income_desc, current_month]]}).execute()

        #get the total earned in the current month
        total_monthly_expense = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                            range= "NetWorth"+ current_year + "!" + chr(date.today().month + 66) + "3").execute()
    
    except IndexError as e:
        await update.message.reply_text(e)
        return ConversationHandler.END

    await update.message.reply_text(selected_income_category + " Expense Updated!\n\nYour total monthly expense is: " + str(total_monthly_expense["values"][0][0]) + "💸 💸")

    return ConversationHandler.END



async def add_category(update: Update, context: CallbackContext) -> int:
    global current_user
    current_user = str(update.message.from_user.id)
    reply_keyboard = [types]

    await update.message.reply_text(
        "Select the category type..., \n\n/cancel to UNDO", 
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return CATEGORY_TYPE


async def add_category_1(update: Update, context: CallbackContext) -> int:
    global new_category_type
    new_category_type = update.message.text
    await update.message.reply_text("Type the new category name, \n\n/cancel to UNDO")

    return CATEGORY_NAME


async def add_category_2(update: Update, context: CallbackContext) -> int:
    global new_category_name
    new_category_name = update.message.text

    text_message = "Category correctly added."
    if new_category_name not in user_categories[current_user][new_category_type]:
        
        user_categories[current_user][new_category_type].append(new_category_name)
        #add to json
        try:
           #with open(directory + "/userCategories.json", 'w', encoding='utf-8') as f: 
            with open('./userCategories.json', 'w', encoding='utf-8') as f:
                json.dump(user_categories, f, ensure_ascii=False, indent=4)
        except:
            print("Unable to write user categories")
    else:
        text_message = "An " + new_category_type.lower() + " category already exists with this name.\n\nTry with a different name."

    await update.message.reply_text(text_message)

    return ConversationHandler.END


def main() -> None:
    """Run the bot."""
    #f = open(directory + "telegramToken.json")
    f = open("./telegramToken.json")
    data = json.load(f)
    application = Application.builder().token(data["token"]).build()

    add_expense_handler = ConversationHandler(
    entry_points=[CommandHandler('add_expense', add_expense)],
    states={
        EXPENSE_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_expense_1)],
        EXPENSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_expense_2)],
        EXPENSE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_expense_3)]

    },
        fallbacks=[MessageHandler(filters.COMMAND, cancel)]
    )

    add_income_handler = ConversationHandler(
    entry_points=[CommandHandler('add_income', add_income)],
    states={
        INCOME_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_income_1)],
        INCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_income_2)],
        INCOME_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_income_3)]

    },
        fallbacks=[MessageHandler(filters.COMMAND, cancel)]
    )

    add_category_handler = ConversationHandler(
    entry_points=[CommandHandler('add_category', add_category)],
    states={
        CATEGORY_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category_1)],
        CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category_2)],

    },
        fallbacks=[MessageHandler(filters.COMMAND, cancel)]
    )   


    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help))
    application.add_handler(add_expense_handler)
    application.add_handler(add_income_handler)
    application.add_handler(add_category_handler)

    # Start the Bot
    application.run_polling()


if __name__ == '__main__':
    main()

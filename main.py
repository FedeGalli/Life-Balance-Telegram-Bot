import logging
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import json
import os
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from google.oauth2 import service_account
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    CallbackContext,
)
from recurring_expenses import (
    RecurringExpenseStore,
    iter_months,
    month_key,
    next_month,
    previous_month,
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def initializeSpreadsheetAPI(spreadsheetLink):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    SERVICE_ACCOUNT_FILE = directory + 'spreadsheetKeys.json'
    credentials = None
    credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    SAMPLE_SPREADSHEET_ID = spreadsheetLink
    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()

    return sheet, SAMPLE_SPREADSHEET_ID

def importUserCategories(directory):
    """Retriving users categories"""
    user_categories = 0
    try:
        f = open(directory + "userCategories.json")
        data = json.load(f)
        user_categories = data
    except IndexError as e:
        print(e)

    return user_categories

def setReplyKeyboard(user_categories):
    reply_keyboard = {}
    for user in user_categories:
        user_categories[user]["Income"].sort()
        user_categories[user]["Expense"].sort()
        reply_keyboard[user] = {"Income" : [], "Expense" : []}
        for type in user_categories[user]:
            tmp_reply_keyboard = []
            for i in range(0, len(user_categories[user][type]), 2):
                if i + 2 <= len(user_categories[user][type]):
                    tmp_reply_keyboard.append(user_categories[user][type][i:i+2])
                else:
                    tmp_reply_keyboard.append(user_categories[user][type][i:i+1])

            reply_keyboard[user][type] = tmp_reply_keyboard

    return reply_keyboard

directory = "./"
data_directory = os.environ.get("BOT_DATA_DIRECTORY", directory)
user_categories = importUserCategories(directory)
reply_keyboard = setReplyKeyboard(user_categories)

EXPENSE_CATEGORY, EXPENSE_DESC, EXPENSE_AMOUNT = range(3)
INCOME_CATEGORY, INCOME_DESC, INCOME_AMOUNT = range(3)
CATEGORY_NAME, CATEGORY_TYPE = range(2)
(
    RECURRING_TYPE,
    RECURRING_CATEGORY,
    RECURRING_AMOUNT,
    RECURRING_DESCRIPTION,
    RECURRING_DELETE_SELECTION,
    RECURRING_DELETE_CONFIRMATION,
) = range(20, 26)

ROME_TIMEZONE = ZoneInfo("Europe/Rome")
SHARED_MEMBERS = {
    "224331200": "Federico",
    "6464119475": "Carolina",
}

recurring_expense_store = RecurringExpenseStore(os.path.join(data_directory, "recurringExpenses.json"))


try:
    f = open(directory + "spreadsheetLinks.json")
    data = json.load(f)
    user_sheet_info = {}
    for element in data:
        tmp_sheet, tmp_sample_spreadsheet_id = initializeSpreadsheetAPI(data[element]["life_balance_link"])
        user_sheet_info[element] = [tmp_sheet, tmp_sample_spreadsheet_id]

except IndexError as e:
    print(e)

#Commands section
async def start(update: Update, context: CallbackContext):

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Welcome, i am glad you are managing your finance, keep it up!!!'
    )


async def help(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Available commands:\n\n"
        "/add_expense - add a manual expense\n"
        "/add_income - add a manual income\n"
        "/add_shared_expense - add a shared expense\n"
        "/add_recurring_expense - schedule a monthly expense\n"
        "/delete_recurring_expense - delete a monthly expense\n"
        "/add_category - add a category\n"
        "/remove_category - remove a category"
    )

async def cancel(update: Update, context: CallbackContext) -> int:
    context.user_data.pop("recurring_expense", None)
    context.user_data.pop("recurring_delete_id", None)
    context.user_data.pop("recurring_delete_labels", None)
    await update.message.reply_text(
        'Current action canceled. \n\nChoose your next action... \n\n', reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def append_expense_row(sheet_key, category, transaction_date, amount, description, creator_name=None):
    sheet, spreadsheet_id = user_sheet_info[sheet_key]
    row = [
        "e",
        category,
        transaction_date,
        amount,
        description,
        datetime.strptime(transaction_date, "%d/%m/%Y").strftime("%b"),
    ]
    if creator_name is not None:
        row.append(creator_name)
    sheet.values().append(
        spreadsheetId=spreadsheet_id,
        range="DB!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


def recurring_targets(expense):
    if expense["type"] == "personal":
        return [(expense["creator_id"], expense["amount"], None)]

    half_amount = str(Decimal(expense["amount"]) / Decimal("2"))
    creator_name = SHARED_MEMBERS.get(expense["creator_id"], expense["creator_id"])
    targets = [(member_id, half_amount, None) for member_id in SHARED_MEMBERS]
    targets.append(("shared", expense["amount"], creator_name))
    return targets


async def process_recurring_expenses(context: CallbackContext):
    now = datetime.now(ROME_TIMEZONE)
    latest_due_date = now.date()
    if now.day == 1 and now.hour < 10:
        latest_due_date = previous_month(latest_due_date)
    current_month = month_key(latest_due_date)

    for snapshot in recurring_expense_store.all():
        for due_month in iter_months(snapshot["start_month"], current_month):
            expense = next(
                (item for item in recurring_expense_store.all() if item["id"] == snapshot["id"]),
                None,
            )
            if expense is None:
                break

            transaction_date = date.fromisoformat(due_month + "-01").strftime("%d/%m/%Y")
            completed = set(expense.get("completed_targets", {}).get(due_month, []))
            targets = recurring_targets(expense)

            for target, amount, creator_name in targets:
                if target in completed:
                    continue
                try:
                    append_expense_row(
                        target,
                        expense["category"],
                        transaction_date,
                        amount,
                        expense["description"],
                        creator_name,
                    )
                    recurring_expense_store.mark_target_completed(expense["id"], due_month, target)
                    completed.add(target)
                except Exception:
                    logger.exception(
                        "Unable to add recurring expense %s to %s for %s",
                        expense["id"], target, due_month,
                    )

            if {target for target, _, _ in targets}.issubset(completed):
                refreshed = next(
                    item for item in recurring_expense_store.all() if item["id"] == expense["id"]
                )
                if due_month not in refreshed.get("notified_months", []):
                    recipients = (
                        SHARED_MEMBERS.keys()
                        if expense["type"] == "shared"
                        else [expense["creator_id"]]
                    )
                    message = (
                        f"Recurring {expense['type']} expense added for {due_month}:\n\n"
                        f"{expense['category']} - €{expense['amount']}\n"
                        f"{expense['description']}"
                    )
                    if expense["type"] == "shared":
                        message += f"\nYour share: €{Decimal(expense['amount']) / Decimal('2')}"
                    try:
                        for recipient in recipients:
                            await context.bot.send_message(chat_id=recipient, text=message)
                        recurring_expense_store.mark_notified(expense["id"], due_month)
                    except Exception:
                        logger.exception("Unable to send recurring expense notification")


async def add_recurring_expense(update: Update, context: CallbackContext) -> int:
    user_id = str(update.effective_user.id)
    choices = [["Personal"]]
    if user_id in SHARED_MEMBERS:
        choices[0].append("Shared")
    context.user_data.pop("recurring_expense", None)
    await update.message.reply_text(
        "Should this monthly expense be personal or shared?\n\n/cancel to cancel",
        reply_markup=ReplyKeyboardMarkup(choices, resize_keyboard=True),
    )
    return RECURRING_TYPE


async def add_recurring_expense_type(update: Update, context: CallbackContext) -> int:
    user_id = str(update.effective_user.id)
    expense_type = update.message.text.strip().lower()
    if expense_type not in {"personal", "shared"} or (
        expense_type == "shared" and user_id not in SHARED_MEMBERS
    ):
        await update.message.reply_text("Please choose Personal or Shared from the keyboard.")
        return RECURRING_TYPE

    context.user_data["recurring_expense"] = {"type": expense_type}
    category_owner = "Shared_Expense" if expense_type == "shared" else user_id
    await update.message.reply_text(
        "Select the expense category.\n\n/cancel to cancel",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard[category_owner]["Expense"],
            resize_keyboard=True,
            input_field_placeholder="Choose...",
        ),
    )
    return RECURRING_CATEGORY


async def add_recurring_expense_category(update: Update, context: CallbackContext) -> int:
    user_id = str(update.effective_user.id)
    recurring = context.user_data["recurring_expense"]
    category_owner = "Shared_Expense" if recurring["type"] == "shared" else user_id
    category = update.message.text.strip()
    if category not in user_categories[category_owner]["Expense"]:
        await update.message.reply_text("Please choose a category from the keyboard.")
        return RECURRING_CATEGORY

    recurring["category"] = category
    await update.message.reply_text(
        "Type the total monthly amount.\n\n/cancel to cancel",
        reply_markup=ReplyKeyboardRemove(),
    )
    return RECURRING_AMOUNT


async def add_recurring_expense_amount(update: Update, context: CallbackContext) -> int:
    raw_amount = update.message.text.strip().replace(",", ".")
    try:
        amount = Decimal(raw_amount)
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await update.message.reply_text("Enter a positive number, for example 25.50.")
        return RECURRING_AMOUNT

    context.user_data["recurring_expense"]["amount"] = format(amount.normalize(), "f")
    await update.message.reply_text("Type a description.\n\n/cancel to cancel")
    return RECURRING_DESCRIPTION


async def add_recurring_expense_description(update: Update, context: CallbackContext) -> int:
    user_id = str(update.effective_user.id)
    recurring = context.user_data.pop("recurring_expense")
    recurring["description"] = update.message.text.strip()
    start_month = month_key(next_month(datetime.now(ROME_TIMEZONE).date()))

    try:
        expense = recurring_expense_store.add(
            recurring["type"], recurring["category"], recurring["amount"],
            recurring["description"], user_id, start_month,
        )
    except RuntimeError as exc:
        await update.message.reply_text(str(exc), reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    message = (
        f"Recurring {expense['type']} expense created.\n\n"
        f"{expense['category']} - €{expense['amount']}\n"
        f"{expense['description']}\nStarts: {expense['start_month']}"
    )
    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())

    if expense["type"] == "shared":
        creator_name = SHARED_MEMBERS[user_id]
        for member_id in SHARED_MEMBERS:
            if member_id != user_id:
                try:
                    await context.bot.send_message(
                        chat_id=member_id,
                        text=f"{creator_name} created a shared recurring expense.\n\n"
                        f"{expense['category']} - €{expense['amount']}\n"
                        f"{expense['description']}\nStarts: {expense['start_month']}",
                    )
                except Exception:
                    logger.exception("Unable to notify shared member about new recurring expense")
    return ConversationHandler.END


def recurring_expense_label(expense):
    label = (
        f"{expense['id'][:6]} | {expense['type'].title()} | "
        f"{expense['category']} | €{expense['amount']} | {expense['description']}"
    )
    return label[:64]


async def delete_recurring_expense(update: Update, context: CallbackContext) -> int:
    user_id = str(update.effective_user.id)
    try:
        expenses = recurring_expense_store.list_for_user(user_id, SHARED_MEMBERS)
    except RuntimeError as exc:
        await update.message.reply_text(str(exc))
        return ConversationHandler.END
    if not expenses:
        await update.message.reply_text("You have no recurring expenses that can be deleted.")
        return ConversationHandler.END

    labels = {recurring_expense_label(expense): expense["id"] for expense in expenses}
    context.user_data["recurring_delete_labels"] = labels
    await update.message.reply_text(
        "Select the recurring expense to delete.\n\n/cancel to cancel",
        reply_markup=ReplyKeyboardMarkup([[label] for label in labels], resize_keyboard=True),
    )
    return RECURRING_DELETE_SELECTION


async def delete_recurring_expense_selection(update: Update, context: CallbackContext) -> int:
    expense_id = context.user_data.get("recurring_delete_labels", {}).get(update.message.text)
    if expense_id is None:
        await update.message.reply_text("Please select an expense from the keyboard.")
        return RECURRING_DELETE_SELECTION
    context.user_data["recurring_delete_id"] = expense_id
    await update.message.reply_text(
        "Delete this recurring expense? Already-added sheet rows will remain.",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], resize_keyboard=True),
    )
    return RECURRING_DELETE_CONFIRMATION


async def delete_recurring_expense_confirmation(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.strip().lower()
    if answer not in {"yes", "no"}:
        await update.message.reply_text("Please choose Yes or No.")
        return RECURRING_DELETE_CONFIRMATION
    if answer == "no":
        context.user_data.pop("recurring_delete_id", None)
        context.user_data.pop("recurring_delete_labels", None)
        await update.message.reply_text("Deletion canceled.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    expense_id = context.user_data.pop("recurring_delete_id", None)
    context.user_data.pop("recurring_delete_labels", None)
    removed = recurring_expense_store.delete(expense_id, user_id, SHARED_MEMBERS)
    if removed is None:
        await update.message.reply_text(
            "That recurring expense no longer exists or you cannot delete it.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    message = (
        f"Recurring {removed['type']} expense deleted:\n\n"
        f"{removed['category']} - €{removed['amount']}\n{removed['description']}"
    )
    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())
    if removed["type"] == "shared":
        deleted_by = SHARED_MEMBERS[user_id]
        for member_id in SHARED_MEMBERS:
            if member_id != user_id:
                try:
                    await context.bot.send_message(
                        chat_id=member_id,
                        text=f"{deleted_by} deleted a shared recurring expense:\n\n"
                        f"{removed['category']} - €{removed['amount']}\n{removed['description']}",
                    )
                except Exception:
                    logger.exception("Unable to notify shared member about recurring expense deletion")
    return ConversationHandler.END

async def add_expense(update: Update, context: CallbackContext) -> int:
    global current_user
    current_user = str(update.message.from_user.id)

    await update.message.reply_text(
        "Select the expense category..., \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard[current_user]["Expense"], resize_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return EXPENSE_CATEGORY

async def add_expense_1(update: Update, context: CallbackContext) -> int:

    await update.message.reply_text("Type the amount spent, \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardRemove()
    )

    global selected_expense_category
    selected_expense_category = update.message.text

    return EXPENSE_AMOUNT

async def add_expense_2(update: Update, context: CallbackContext) -> int:

    global selected_expense_amount
    selected_expense_amount = update.message.text

    if not all([c.isdigit() or c == '.' for c in selected_expense_amount]):
        await update.message.reply_text(selected_expense_amount + " is not a valid expense number, action canceled!!!\n\n/add_expense to retry.")
        return ConversationHandler.END

    await update.message.reply_text("Type a description, \n\n/cancel to UNDO")

    return EXPENSE_DESC

async def add_expense_3(update: Update, context: CallbackContext) -> int:
    current_year = str(date.today().year)
    current_date = str(date.today().strftime("%d/%m/%Y"))
    current_month = str(date.today().strftime("%b"))
    global selected_expense_desc
    selected_expense_desc = update.message.text

    sheet, SAMPLE_SPREADSHEET_ID = user_sheet_info[current_user][0], user_sheet_info[current_user][1]

    try:

        sheet.values().append(spreadsheetId=SAMPLE_SPREADSHEET_ID,
            range= "DB!A1" , valueInputOption="USER_ENTERED", body={"values":[['e', selected_expense_category, current_date, selected_expense_amount, selected_expense_desc, current_month]]}).execute()

        #get the total spent in the current month
        total_monthly_expense = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                            range= "Expenses"+ current_year + "!" + chr(date.today().month + 65) + "28").execute()

    except IndexError as e:
        await update.message.reply_text(e)
        return ConversationHandler.END

    await update.message.reply_text(selected_expense_category + " Expense Updated!\n\nYour total monthly expense is: " + str(total_monthly_expense["values"][0][0]) + "💸 💸")

    return ConversationHandler.END

async def add_shared_expense(update: Update, context: CallbackContext) -> int:
    global current_user
    current_user = str(update.message.from_user.id)

    if current_user not in ["6464119475", "224331200"]:
        await update.message.reply_text("You are not allowed!!!")
        return ConversationHandler.END

    await update.message.reply_text(
        "Select the shared expense category..., \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard["Shared_Expense"]["Expense"], resize_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return EXPENSE_CATEGORY

async def add_shared_expense_1(update: Update, context: CallbackContext) -> int:

    await update.message.reply_text("Type the amount spent, \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardRemove()
    )

    global selected_expense_category
    selected_expense_category = update.message.text

    return EXPENSE_AMOUNT

async def add_shared_expense_2(update: Update, context: CallbackContext) -> int:

    global selected_expense_amount
    selected_expense_amount = update.message.text

    if not all([c.isdigit() or c == '.' for c in selected_expense_amount]):
        await update.message.reply_text(selected_expense_amount + " is not a valid expense number, action canceled!!!\n\n/add_shared_expense to retry.")
        return ConversationHandler.END

    await update.message.reply_text("Type a description, \n\n/cancel to UNDO")

    return EXPENSE_DESC

async def add_shared_expense_3(update: Update, context: CallbackContext) -> int:
    current_year = str(date.today().year)
    current_date = str(date.today().strftime("%d/%m/%Y"))
    current_month = str(date.today().strftime("%b"))
    global selected_expense_desc
    selected_expense_desc = update.message.text


    user_name = ""
    other_user = ""


    if current_user == "224331200":
        user_name = "Federico"
        other_user = "6464119475"
    else:
        user_name = "Carolina"
        other_user = "224331200"

    shared_sheet, SHARED_SAMPLE_SPREADSHEET_ID = user_sheet_info["shared"][0], user_sheet_info["shared"][1]
    other_shared_sheet, OTHER_SHARED_SAMPLE_SPREADSHEET_ID = user_sheet_info[other_user][0], user_sheet_info[other_user][1]
    sheet, SAMPLE_SPREADSHEET_ID = user_sheet_info[current_user][0], user_sheet_info[current_user][1]

    try:

        sheet.values().append(spreadsheetId=SAMPLE_SPREADSHEET_ID,
            range= "DB!A1" , valueInputOption="USER_ENTERED", body={"values":[['e', selected_expense_category, current_date, float(selected_expense_amount) / 2, selected_expense_desc, current_month]]}).execute()

        #get the total spent in the current month
        total_monthly_expense = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                            range= "Expenses"+ current_year + "!" + chr(date.today().month + 65) + "28").execute()

        #get the total spent in the current month
        other_total_monthly_expense = sheet.values().get(spreadsheetId=OTHER_SHARED_SAMPLE_SPREADSHEET_ID,
                            range= "Expenses"+ current_year + "!" + chr(date.today().month + 65) + "28").execute()

        other_shared_sheet.values().append(spreadsheetId=OTHER_SHARED_SAMPLE_SPREADSHEET_ID,
            range= "DB!A1" , valueInputOption="USER_ENTERED", body={"values":[['e', selected_expense_category, current_date, float(selected_expense_amount) / 2, selected_expense_desc, current_month]]}).execute()

        shared_sheet.values().append(spreadsheetId=SHARED_SAMPLE_SPREADSHEET_ID,
            range= "DB!A1" , valueInputOption="USER_ENTERED", body={"values":[['e', selected_expense_category, current_date, selected_expense_amount, selected_expense_desc, current_month, user_name]]}).execute()


    except IndexError as e:
        await update.message.reply_text(e)
        return ConversationHandler.END

    await update.message.reply_text("Shared expense Insert!\n\n" + selected_expense_category + " " + str(float(selected_expense_amount)/2) + "€ " + selected_expense_desc + "\n\nYour total monthly expense is: " + str(total_monthly_expense["values"][0][0]) + "💸 💸")
    # Sending a message to another user
    await context.bot.send_message(
        chat_id=other_user,
        text= selected_expense_category + " Shared expense Insert by " + user_name + "❤️\n\n" + selected_expense_category + " " + str(float(selected_expense_amount)/2) + "€ " + selected_expense_desc + "\n\nYour total monthly expense is: " + str(other_total_monthly_expense["values"][0][0]) + "💸 💸"
    )

    return ConversationHandler.END


async def add_income(update: Update, context: CallbackContext) -> int:
    global current_user
    current_user = str(update.message.from_user.id)

    await update.message.reply_text(
        "Select the income category... \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard[current_user]["Income"], resize_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return INCOME_CATEGORY

async def add_income_1(update: Update, context: CallbackContext) -> int:

    await update.message.reply_text("Type the amount earned, \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardRemove()
    )

    global selected_income_category
    selected_income_category = update.message.text

    return INCOME_AMOUNT

async def add_income_2(update: Update, context: CallbackContext) -> int:

    global selected_income_amount
    selected_income_amount = update.message.text

    if not all([c.isdigit() or c == '.' for c in selected_income_amount]):
        await update.message.reply_text(selected_income_amount + " is not a valid income number, action canceled!!!\n\n/add_income to retry.")
        return ConversationHandler.END
    await update.message.reply_text("Type a description, \n\n/cancel to UNDO")

    return INCOME_DESC

async def add_income_3(update: Update, context: CallbackContext) -> int:
    current_year = str(date.today().year)
    current_date = str(date.today().strftime("%d/%m/%Y"))
    current_month = str(date.today().strftime("%b"))
    global selected_income_desc
    selected_income_desc = update.message.text

    sheet, SAMPLE_SPREADSHEET_ID = user_sheet_info[current_user][0], user_sheet_info[current_user][1]

    try:

        sheet.values().append(spreadsheetId=SAMPLE_SPREADSHEET_ID,
            range= "DB!A1" , valueInputOption="USER_ENTERED", body={"values":[['i', selected_income_category, current_date, selected_income_amount, selected_income_desc, current_month]]}).execute()

        #get the total earned in the current month
        total_monthly_expense = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                            range= "NetWorth"+ current_year + "!" + chr(date.today().month + 66) + "3").execute()

    except IndexError as e:
        await update.message.reply_text(e)
        return ConversationHandler.END

    await update.message.reply_text(selected_income_category + " Income Updated!\n\nYour total monthly income is: " + str(total_monthly_expense["values"][0][0]) + "💸 💸")

    return ConversationHandler.END



async def add_category(update: Update, context: CallbackContext) -> int:
    global current_user
    current_user = str(update.message.from_user.id)
    reply_keyboard_type = [['Income', 'Expense']]

    await update.message.reply_text(
        "Select the category type... \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard_type, resize_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return CATEGORY_TYPE


async def add_category_1(update: Update, context: CallbackContext) -> int:

    await update.message.reply_text(
        "Type the new category name, \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardRemove()
    )
    global new_category_type
    new_category_type = update.message.text

    return CATEGORY_NAME

async def add_category_2(update: Update, context: CallbackContext) -> int:
    global new_category_name
    new_category_name = update.message.text
    global reply_keyboard

    text_message = "Category correctly added."
    if new_category_name not in user_categories[current_user][new_category_type]:

        user_categories[current_user][new_category_type].append(new_category_name)
        reply_keyboard = setReplyKeyboard(user_categories)
        #add to json
        try:
           with open(directory + "/userCategories.json", 'w', encoding='utf-8') as f:
                json.dump(user_categories, f, ensure_ascii=False, indent=4)
        except:
            print("Unable to write user categories")
    else:
        text_message = "An " + new_category_type.lower() + " category already exists with this name.\n\nTry with a different name."

    await update.message.reply_text(text_message)

    return ConversationHandler.END

async def remove_category(update: Update, context: CallbackContext) -> int:
    global current_user
    current_user = str(update.message.from_user.id)
    reply_keyboard_type = [['Income', 'Expense']]

    await update.message.reply_text(
        "Select the category type to remove... \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard_type, resize_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return CATEGORY_TYPE

async def remove_category_1(update: Update, context: CallbackContext) -> int:
    global remove_category_type
    remove_category_type = update.message.text


    await update.message.reply_text(
        "Select the category to remove... \n\n/cancel to UNDO",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard[current_user][remove_category_type], resize_keyboard=True, input_field_placeholder='Choose...'
        ),
    )

    return CATEGORY_NAME

async def remove_category_2(update: Update, context: CallbackContext) -> int:
    global remove_category_name
    remove_category_name = update.message.text
    global reply_keyboard

    user_categories[current_user][remove_category_type].remove(remove_category_name)
    reply_keyboard = setReplyKeyboard(user_categories)
    #add to json
    try:
       with open(directory + "/userCategories.json", 'w', encoding='utf-8') as f:
            json.dump(user_categories, f, ensure_ascii=False, indent=4)

    except:
        print("Unable to write user categories")

    await update.message.reply_text(
        "Category correctly removed.",
        reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END



def main() -> None:
    """Run the bot."""
    f = open(directory + "telegramToken.json")
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

    add_shared_expense_handler = ConversationHandler(
    entry_points=[CommandHandler('add_shared_expense', add_shared_expense)],
    states={
        EXPENSE_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_shared_expense_1)],
        EXPENSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_shared_expense_2)],
        EXPENSE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_shared_expense_3)]

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

    remove_category_handler = ConversationHandler(
    entry_points=[CommandHandler('remove_category', remove_category)],
    states={
        CATEGORY_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_category_1)],
        CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_category_2)],

    },
        fallbacks=[MessageHandler(filters.COMMAND, cancel)]
    )

    add_recurring_expense_handler = ConversationHandler(
        entry_points=[CommandHandler('add_recurring_expense', add_recurring_expense)],
        states={
            RECURRING_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_recurring_expense_type)],
            RECURRING_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_recurring_expense_category)],
            RECURRING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_recurring_expense_amount)],
            RECURRING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_recurring_expense_description)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel)],
    )

    delete_recurring_expense_handler = ConversationHandler(
        entry_points=[CommandHandler('delete_recurring_expense', delete_recurring_expense)],
        states={
            RECURRING_DELETE_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_recurring_expense_selection)],
            RECURRING_DELETE_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_recurring_expense_confirmation)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel)],
    )


    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help))
    application.add_handler(add_expense_handler)
    application.add_handler(add_shared_expense_handler)
    application.add_handler(add_recurring_expense_handler)
    application.add_handler(delete_recurring_expense_handler)
    application.add_handler(add_income_handler)
    application.add_handler(add_category_handler)
    application.add_handler(remove_category_handler)
    application.job_queue.run_once(process_recurring_expenses, when=1)
    application.job_queue.run_monthly(
        process_recurring_expenses,
        when=time(hour=10, minute=0, tzinfo=ROME_TIMEZONE),
        day=1,
        name="process-recurring-expenses",
    )

    # Start the Bot
    application.run_polling()


if __name__ == '__main__':
    main()

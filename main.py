import json
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, PollAnswerHandler, ContextTypes
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Установка констант из переменных окружения
TOKEN = os.getenv('TG_TOKEN')

# Загрузим вопросы из файла
with open('questions.json', 'r', encoding='utf-8') as file:
    QUESTIONS = json.load(file)

# Перемешаем вопросы
random.shuffle(QUESTIONS)

current_question = 0  # Индекс текущего вопроса

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global current_question
    current_question = 0
    context.user_data['message'] = update.message
    await ask_question(update, context)

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global current_question
    current_question += 1
    if current_question < len(QUESTIONS):
        await ask_question(update, context)
    else:
        if 'message' in context.user_data:
            await context.user_data['message'].reply_text("Вы ответили на все вопросы. Викторина завершена!")

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question_data = QUESTIONS[current_question]
    options = list(question_data['options'].values())
    correct_option_index = list(question_data['options'].keys()).index(question_data['correct_answer'])

    if 'message' in context.user_data:
        message = context.user_data['message']
    else:
        message = update.message if update.message else update.callback_query.message
        context.user_data['message'] = message

    await message.reply_poll(
        question=question_data['question'],
        options=options,
        type='quiz',
        correct_option_id=correct_option_index,
        explanation=question_data['quote'][:150],
        is_anonymous=False
    )

    if len(question_data['quote']) > 150:
        context.user_data['full_quote'] = question_data['quote']

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await next_question(update, context)

async def handle_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'full_quote' in context.user_data:
        await update.message.reply_text(context.user_data['full_quote'])
        context.user_data.pop('full_quote', None)

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    print("Бот запущен")
    try:
        application.run_polling()
    finally:
        print("Бот остановлен")

if __name__ == '__main__':
    main()
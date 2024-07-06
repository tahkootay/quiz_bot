import json
import os
#import random
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, PollAnswerHandler, ContextTypes, MessageHandler, filters
)
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Установка констант из переменных окружения
TOKEN = os.getenv('TG_TOKEN')
ACCESS_MODE = os.getenv('ACCESS_MODE', 'restricted')  # 'open' для доступа для всех, 'restricted' для только разрешённых пользователей

# Загрузка id разрешенных пользователей из .env и преобразование в список чисел
ALLOWED_USERS = list(map(int, os.getenv('ALLOWED_USERS', '').split(','))) if ACCESS_MODE == 'restricted' else []

# Загрузим вопросы из файла
with open('quest_courier.json', 'r', encoding='utf-8') as file:
#with open('questions.json', 'r', encoding='utf-8') as file:
    QUESTIONS = json.load(file)

# Перемешаем вопросы
#random.shuffle(QUESTIONS)

current_question = 0  # Индекс текущего вопроса

def access_control(func):
    async def wrapped(update, context):
        if ACCESS_MODE == 'restricted' and update.effective_user.id not in ALLOWED_USERS:
            await update.message.reply_text('К сожалению, у вас нет доступа к этому боту.')
            return
        return await func(update, context)
    return wrapped

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global current_question
    current_question = 0
    context.user_data['correct_answers'] = 0
    context.user_data['answered_questions'] = 0
    context.user_data['message'] = update.message
    await ask_question(update, context)

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global current_question
    current_question += 1
    if current_question < len(QUESTIONS):
        await ask_question(update, context)
    else:
        results = f"Всего отвечено вопросов: {context.user_data['answered_questions']}\nКоличество правильных ответов: {context.user_data['correct_answers']}"
        if 'message' in context.user_data:
            await context.user_data['message'].reply_text(f"Вы ответили на все вопросы. Викторина завершена!\n\n{results}")

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question_data = QUESTIONS[current_question]
    options = list(question_data['options'].values())
    correct_option_index = list(question_data['options'].keys()).index(question_data['correct_answer'])
    context.user_data['correct_option_index'] = correct_option_index

    if 'message' in context.user_data:
        message = context.user_data['message']
    else:
        message = update.message if update.message else update.callback_query.message
        context.user_data['message'] = message

    poll_message = await message.reply_poll(
        question=question_data['question'],
        options=options,
        type='quiz',
        correct_option_id=correct_option_index,
        explanation=question_data['quote'][:150],
        is_anonymous=False
    )

    if len(question_data['quote']) > 150:
        context.user_data['full_quote'] = f"Полная цитата: {question_data['quote']}"

    context.user_data['poll_message'] = poll_message
    context.user_data['poll_message_id'] = poll_message.message_id
    context.user_data['chat_id'] = poll_message.chat_id
    context.user_data['time_left'] = 30  # Начальное время (30 секунд)

    job = context.job_queue.run_repeating(countdown_timer, interval=1, first=0,
                                          context={'chat_id': poll_message.chat_id,
                                                   'message_id': poll_message.message_id,
                                                   'update': update,
                                                   'context': context})
    context.user_data['job'] = job

async def countdown_timer(context):
    chat_id = context.job.context['chat_id']
    poll_message_id = context.job.context['message_id']
    time_left = context.job.context['context'].user_data['time_left']

    if time_left > 0:
        context.job.context['context'].user_data['time_left'] -= 1
        text = f"Осталось времени: {time_left} секунд"
        try:
            await context.bot.edit_message_text(text=text, chat_id=chat_id, message_id=poll_message_id + 1)
        except:
            pass
    else:
        # Если время закончилось, удаляем вопрос
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=poll_message_id)
        except:
            pass
        await next_question(context.job.context['update'], context.job.context['context'])

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    answered_poll = update.poll_answer
    selected_option = answered_poll.option_ids[0]
    correct_option_index = context.user_data['correct_option_index']

    context.user_data['answered_questions'] += 1

    if selected_option == correct_option_index:
        context.user_data['correct_answers'] += 1

    if 'full_quote' in context.user_data:
        await context.user_data['message'].reply_text(context.user_data['full_quote'])
        context.user_data.pop('full_quote', None)

    await next_question(update, context)

async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    results = f"Всего отвечено вопросов: {context.user_data['answered_questions']}\nКоличество правильных ответов: {context.user_data['correct_answers']}"
    await update.message.reply_text(results)

async def handle_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'full_quote' in context.user_data:
        await update.message.reply_text(context.user_data['full_quote'])
        context.user_data.pop('full_quote', None)

if __name__ == '__main__':
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler("results", show_results))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quote))

    print("Бот запущен")
    try:
        application.run_polling()
    finally:
        print("Бот остановлен")

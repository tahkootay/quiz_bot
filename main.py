import json
import os
import asyncio
from datetime import datetime
from telegram import Update, Poll
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, PollAnswerHandler, CallbackQueryHandler, JobQueue
from telegram.ext import CallbackContext, PollAnswerHandler

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
    QUESTIONS = json.load(file)

current_question = 0  # Индекс текущего вопроса

def access_control(func):
    async def wrapped(update, context):
        if ACCESS_MODE == 'restricted' and update.effective_user.id not in ALLOWED_USERS:
            await update.message.reply_text('К сожалению, у вас нет доступа к этому боту.')
            return
        return await func(update, context)
    return wrapped

# Асинхронная функция старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Функция start вызвана. User ID: {update.effective_user.id}, Message ID: {update.message.message_id}")
    if context.user_data.get('quiz_started'):
        #await update.message.reply_text("Викторина уже запущена. Используйте /stop, чтобы остановить текущую викторину.")
        return
    context.user_data['quiz_started'] = True  
    global current_question
    current_question = 0
    context.user_data['correct_answers'] = 0
    context.user_data['answered_questions'] = 0
    context.user_data['message'] = update.message
    context.user_data['start_time'] = asyncio.get_event_loop().time()  # Запоминаем время начала викторины
    
    user = update.effective_user
    
    # Получаем текущее время
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Получаем данные пользователя
    user_id = user.id
    user_name = user.username if user.username else "не указан"
    
    # Формируем строку для логирования
    log_entry = f"Date time: {current_datetime}: @{user_name} ({user_id})\n"
    
    # Записываем лог в файл (добавляем, не перезаписываем)
    with open('start_logs.txt', 'a', encoding='utf-8') as file:
        file.write(log_entry)
    
    # Получаем имя пользователя, никнейм или приветствие по умолчанию
    theme = 'по фильму "Курьер"'
    if user.first_name:
        greet_user = f"Добро пожаловать, {user.first_name}!"
    elif user.username:
        greet_user = f"Добро пожаловать, @{user.username}!"
    else:
        greet_user = "Добро пожаловать!"
    
    # Отправляем приветственное сообщение
    await update.message.reply_text(f'{greet_user} Тебе предстоит ответить на вопросы {theme}. Всего вопросов в квизе: {len(QUESTIONS)}. На каждый вопрос даётся 30 секунд. Остановить бота можно командой /stop. Удачи!')
    # Запускаем таймер перед первым вопросом
    #context.user_data['time_left'] = 15  # Устанавливаем начальное время
    #job = context.job_queue.run_repeating(countdown_timer, interval=1, first=0,
                                        #   data={'chat_id': update.effective_chat.id,
                                        #         'message_id': None,
                                        #         'update': update,
                                        #         'context': context})
    #context.user_data['job'] = job   
    # Начинаем задавать вопросы
    await ask_question(update, context)

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global current_question
    print(f"Текущий вопрос: {current_question}")
    
    if current_question >= len(QUESTIONS):
        await show_results(update, context)
        return

    question_data = QUESTIONS[current_question]
    options = list(question_data['options'].values())
    correct_option_index = list(question_data['options'].keys()).index(question_data['correct_answer'])
    context.user_data['correct_option_index'] = correct_option_index

    message = context.user_data.get('message', update.message if update.message else update.callback_query.message if update.callback_query else None)
    if message is None:
        print("Ошибка: не удалось получить объект сообщения")
        return

    context.user_data['message'] = message

    try:
        poll_message = await message.reply_poll(
            question=question_data['question'],
            options=options,
            type=Poll.QUIZ,
            correct_option_id=correct_option_index,
            explanation=question_data['quote'][:150],
            is_anonymous=False
        )
    except Exception as e:
        print(f"Ошибка при отправке опроса: {e}")
        return

    if len(question_data['quote']) > 150:
        context.user_data['full_quote'] = f"Полная цитата: {question_data['quote']}"

    context.user_data.update({
        'poll_message': poll_message,
        'poll_message_id': poll_message.message_id,
        'chat_id': poll_message.chat_id,
        'time_left': 30,  # Начальное время (30 секунд)
    })

    # Удаление предыдущего таймерного сообщения, если оно существует
    if 'time_message_id' in context.user_data:
        try:
            await context.bot.delete_message(context.user_data['chat_id'], context.user_data.pop('time_message_id'))
        except Exception as e:
            print(f"Ошибка при удалении предыдущего таймерного сообщения: {e}")

    # Остановка предыдущего таймера, если он существует
    if 'job' in context.user_data:
        try:
            context.user_data['job'].schedule_removal()
        except Exception as e:
            print(f"Ошибка при остановке предыдущего таймера: {e}")
        context.user_data.pop('job', None)

    job = context.job_queue.run_repeating(countdown_timer, interval=1, first=0,
                                          data={'chat_id': poll_message.chat_id,
                                                'message_id': poll_message.message_id,
                                                'update': update,
                                                'context': context})
    context.user_data['job'] = job

    print("Следующий вопрос задан")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("Получен ответ на опрос")
    answered_poll = update.poll_answer
    selected_option = answered_poll.option_ids[0]
    correct_option_index = context.user_data.get('correct_option_index')

    if correct_option_index is None:
        print("Ошибка: correct_option_index не найден")
        return

    context.user_data['answered_questions'] = context.user_data.get('answered_questions', 0) + 1

    if selected_option == correct_option_index:
        context.user_data['correct_answers'] = context.user_data.get('correct_answers', 0) + 1

    if 'full_quote' in context.user_data:
        await context.user_data['message'].reply_text(context.user_data['full_quote'])
        context.user_data.pop('full_quote', None)

    # Остановка текущего таймера
    if 'job' in context.user_data:
        try:
            context.user_data['job'].schedule_removal()
        except Exception as e:
            print(f"Ошибка при остановке таймера: {e}")
        context.user_data.pop('job', None)

    # Удаление сообщения с таймером, если оно существует
    if 'time_message_id' in context.user_data and 'chat_id' in context.user_data:
        try:
            await context.bot.delete_message(context.user_data['chat_id'], context.user_data.pop('time_message_id'))
        except Exception as e:
            print(f"Ошибка при удалении сообщения с таймером: {e}")

    print("Вызываем next_question из handle_poll_answer")
    await next_question(update, context)

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global current_question
    current_question += 1
    print(f"Переходим к следующему вопросу: {current_question}")
    
    # Остановка предыдущего таймера, если он существует
    if 'job' in context.user_data:
        try:
            context.user_data['job'].schedule_removal()
        except Exception as e:
            print(f"Ошибка при остановке таймера: {e}")
        context.user_data.pop('job', None)
    
    if current_question < len(QUESTIONS):
        print("Задаем следующий вопрос")
        await ask_question(update, context)
    else:
        await show_results(update, context)

async def countdown_timer(context: ContextTypes.DEFAULT_TYPE) -> None:
    job_data = context.job.data
    chat_id = job_data['chat_id']
    poll_message_id = job_data['message_id']
    time_left = job_data['context'].user_data['time_left']

    if time_left > 0:
        job_data['context'].user_data['time_left'] -= 1
        text = f"Оставшееся время: {time_left} сек."
        
        if 'time_message_id' in job_data['context'].user_data:
            time_message_id = job_data['context'].user_data['time_message_id']
            try:
                await context.bot.edit_message_text(text=text, chat_id=chat_id, message_id=time_message_id)
            except Exception as e:
                print(f"Ошибка при редактировании сообщения: {e}")
        else:
            time_message = await context.bot.send_message(chat_id=chat_id, text=text)
            job_data['context'].user_data['time_message_id'] = time_message.message_id
    else:
        # Остановка текущего таймера
        context.job.schedule_removal()
        
        if 'time_message_id' in job_data['context'].user_data:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=job_data['context'].user_data.pop('time_message_id'))
            except Exception as e:
                print(f"Ошибка при удалении сообщения с временем: {e}")

        try:
            await context.bot.stop_poll(chat_id, poll_message_id)
        except Exception as e:
            print(f"Ошибка при закрытии опроса: {e}")
        
        print("Таймер завершен, переходим к следующему вопросу")
        await next_question(job_data['update'], job_data['context'])

async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE, is_manual_stop: bool = False) -> None:
    end_time = asyncio.get_event_loop().time()
    total_time = end_time - context.user_data['start_time']
    minutes, seconds = divmod(int(total_time), 60)
    time_spent = f"{minutes:02}:{seconds:02}"

    # Получаем текущую дату и время
    end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Получаем данные пользователя
    user = update.effective_user
    user_id = user.id
    user_name = user.username if user.username else "не указан"

    # Формируем результаты для пользователя (без изменений)
    results_for_user = (
        f"Общее количество вопросов: {len(QUESTIONS)}\n"
        f"Всего отвечено вопросов: {context.user_data.get('answered_questions', 0)}\n"
        f"Количество правильных ответов: {context.user_data.get('correct_answers', 0)}\n"
        f"Затраченное время: {time_spent}."
    )
    
    # Формируем результаты для сохранения в файл (с добавлением даты и времени)
    results_for_file = (
        f"Дата и время: {end_datetime}\n"
        f"Ник пользователя: {user_name} ({user_id})\n"
        f"Общее количество вопросов: {len(QUESTIONS)}\n"
        f"Всего отвечено вопросов: {context.user_data.get('answered_questions', 0)}\n"
        f"Количество правильных ответов: {context.user_data.get('correct_answers', 0)}\n"
        f"Затраченное время: {time_spent}.\n"
    )
    
    # Отправляем сообщение пользователю
    if is_manual_stop:
        message_for_user = f"Викторина остановлена. Чтобы начать заново, используйте команду /start\n\n{results_for_user}"
    else:
        message_for_user = f"Вы ответили на все вопросы. Викторина завершена!\n\n{results_for_user}"

    # Отправляем сообщение пользователю
    await context.user_data['message'].reply_text(message_for_user)
    # Сохраняем результаты в файл (добавляем, не перезаписываем) (без изменений)
    with open('quiz_results.txt', 'a', encoding='utf-8') as file:
        file.write(f"{results_for_file}\n---\n")

async def handle_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'full_quote' in context.user_data:
        await update.message.reply_text(context.user_data['full_quote'])
        context.user_data.pop('full_quote', None)

async def stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['quiz_started'] = False
    print("Викторина остановлена")
    # Остановка текущего таймера
    if 'job' in context.user_data:
        context.user_data['job'].schedule_removal()
        context.user_data.pop('job', None)
    
    # Удаление сообщения с таймером, если оно существует
    if 'time_message_id' in context.user_data and 'chat_id' in context.user_data:
        try:
            await context.bot.delete_message(context.user_data['chat_id'], context.user_data.pop('time_message_id'))
        except Exception as e:
            print(f"Ошибка при удалении сообщения с таймером: {e}")
    
    # Показываем результаты с флагом ручной остановки
    await show_results(update, context, is_manual_stop=True)
    
    #await update.message.reply_text("Викторина остановлена. Чтобы начать заново, используйте команду /start")

if __name__ == '__main__':
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler("results", show_results))
    application.add_handler(CommandHandler("stop", stop_quiz))  # Добавьте эту строку    
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quote))

    print("Бот запущен")
    try:
        application.run_polling()
    finally:
        print("Бот остановлен")

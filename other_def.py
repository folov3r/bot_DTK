import asyncio
import logging
import os
from datetime import date, timedelta
import yadisk
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from docx import Document
from dotenv import load_dotenv
from cache_schedule import schedule_cache
from db_def import *

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_TEST")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

yadisk_client = yadisk.Client(token=YANDEX_TOKEN)



def check_and_notify(file_name, update: bool = False):
    with sqlite3.connect("db/notifications.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT notified FROM notifications WHERE file_name = ?", (file_name,))
        result = cursor.fetchone()
        users = get_all_users_id()
        splited_name = file_name.split(".docx")[0]
        for user_id in users:
            if not result or not result[0] and update == False:
                asyncio.create_task(send_notification(user_id, f"📥 {splited_name} загружено на сервер."))
                cursor.execute("""
                INSERT OR REPLACE INTO notifications (file_name, notified)
                VALUES (?, ?)
            """, (file_name, True))
                conn.commit()
            elif result and update == True:
                asyncio.create_task(send_notification(user_id, f"⚠️📥 {splited_name} изменилось и было загружено на сервер."))


allowed_groups = [
    "10", "11.1", "11.2", "12", "13", "14", "15", "16", "17", "18", "19",
    "КСК-1", "ОП-1", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "КСК-2", "ОП-2", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "КСК-3", "ОП-3", "40.1", "40.2", "41", "42", "43", "44", "45", "101", "102", "201", "202", "203"
]


def validate_and_correct_group(user_input):
    user_input = user_input.upper()

    if user_input in allowed_groups:
        return user_input, True

    for group in allowed_groups:
        if user_input.replace(" ", "-") == group or user_input == group.replace("-", " "):
            return group, True

    if user_input.isdigit():
        for group in allowed_groups:
            if group.isdigit() and group == user_input:
                return group, True

    return None, False


def create_keyboard(buttons):
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=btn) for btn in row] for row in buttons],
        resize_keyboard=True
    )


main_keyboard = create_keyboard([
    ["Проверить расписание", "Расписание звонков"],
    ["Профиль"]
])

schedule_keyboard = create_keyboard([
    ["Сегодня", "Завтра"],
    ["После завтра", "Другая дата"],
    ["Другая группа"],
    ["Отмена"]
])

schedule_keyboard_another_group = create_keyboard([
    ["Сегодня", "Завтра"],
    ["После завтра", "Другая дата"],
    ["Вернуться"]
])

cancel_keyboard = create_keyboard([["Отмена"]])

return_keyboard = create_keyboard([["Вернуться"]])

profile_keyboard = create_keyboard([
    ["Изменить данные", "Удалить аккаунт"],
    ["Авто рассылка", "Избранные группы"],  # Новая кнопка
    ["Обратная связь"],
    ["Вернуться"]
])

login_lvl_1_keyboard = create_keyboard([["/login"]])

yes_no_keyboard = create_keyboard([["Да", "Нет"]])

back_feedback_keyboard = create_keyboard([["Вернуться на главную"]])

choose_list_users = create_keyboard([["Студентов",'Преподавателей']])

def create_favorite_groups_keyboard(user_id: int):
    favorite_groups = get_favorite_groups(user_id)
    buttons = [[InlineKeyboardButton(text=group, callback_data=f"remove_favorite_{group}")] for group in favorite_groups]
    buttons.append([InlineKeyboardButton(text="Добавить группу", callback_data="add_favorite_group")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_profile")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def process_schedule_file(file_path):
    target_date = file_path.split("/")[-1]

    if target_date in schedule_cache:
        # Проверяем актуальность кеша
        current_hash = get_file_hash(file_path)
        cached_hash = schedule_cache[target_date].get("hash") if isinstance(schedule_cache[target_date], dict) else None
        if cached_hash == current_hash:
            logging.info(f"Используется кеш для даты {target_date}")
            return schedule_cache[target_date]
        else:
            logging.info("Расписание изменилось, обновление кеша")

    schedule_data = {}
    teacher_schedule_data = {}
    doc = Document(file_path)
    current_group = None

    def add_schedule_entry(group, pair_number, subject, teacher, room):
        if group not in schedule_data:
            schedule_data[group] = []

        if teacher and teacher not in teacher_schedule_data:
            teacher_schedule_data[teacher] = {}

        if subject in ["Практика", "Разговоры о важном", "Сессия"]:
            schedule_entry = f"|{pair_number} {subject}|"
        elif subject or teacher or room:
            schedule_entry = f"|{pair_number} {subject}| |{teacher}| |{room}|"
        else:
            schedule_entry = f"|{pair_number} Нет пары|"

        schedule_data[group].append((pair_number, schedule_entry))

        if teacher:
            if group not in teacher_schedule_data[teacher]:
                teacher_schedule_data[teacher][group] = []
            teacher_entry = f"|{pair_number} {subject}| |{room}|"
            teacher_schedule_data[teacher][group].append((pair_number, teacher_entry))

    try:
        for table in doc.tables:
            rows = list(table.rows)
            for i, row in enumerate(rows):
                cells = [cell.text.strip() if cell.text else "" for cell in row.cells]
                if len(cells) >= 3:
                    if cells[0]:
                        current_group = cells[0]
                    elif not cells[0] and not cells[1] and not cells[2] and not cells[3] and not cells[4]:
                        current_group = None
                        continue

                    if current_group:
                        teacher = cells[3] if len(cells) > 3 else None
                        room = cells[4] if len(cells) > 4 else None
                        add_schedule_entry(current_group, cells[1], cells[2], teacher, room)

        for group in schedule_data:
            pairs = schedule_data[group]
            last_filled_index = -1
            for i, (pair_number, entry) in enumerate(pairs):
                if not entry.endswith("Нет пары|"):
                    last_filled_index = i

            if last_filled_index != -1:
                schedule_data[group] = pairs[:last_filled_index + 1]

        for group in schedule_data:
            schedule_data[group] = "\n".join([entry[1] for entry in schedule_data[group]])

        for teacher in teacher_schedule_data:
            for group in teacher_schedule_data[teacher]:
                teacher_schedule_data[teacher][group].sort(
                    key=lambda x: int(x[0].split('.')[0]) if x[0].split('.')[0].isdigit() else 0)
                teacher_schedule_data[teacher][group] = "\n".join(
                    [entry[1] for entry in teacher_schedule_data[teacher][group]])

        schedule_cache[target_date] = (schedule_data, teacher_schedule_data)
        logging.info(f"Данные для даты {target_date} добавлены в кеш")

        result = {
            "data": (schedule_data, teacher_schedule_data),
            "hash": get_file_hash(file_path)
        }

        schedule_cache[target_date] = result
        logging.info(f"Данные для даты {target_date} добавлены в кеше")

        return schedule_data, teacher_schedule_data

    except Exception as e:
        logging.error(f"Ошибка при обработке файла: {e}")
        return None, None


def save_user_data(user_id, username, value, is_teacher=0):
    db_execute("users", """
        INSERT OR REPLACE INTO users (user_id, username, value, is_teacher)
        VALUES (?, ?, ?, ?)
    """, (user_id, username, value, is_teacher))


def get_user_data(user_id):
    result = db_fetch("users", "SELECT value, is_teacher, notifications_enabled FROM users WHERE user_id = ?",(user_id,))
    return result[0] if result else (None, None, None)

async def save_list_users(message: types.Message, users: list):
    with open("users_list.txt", "w", encoding="utf-8-sig") as file:
        count_users = len(users)
        students = [user for user in users if user[3] == 0]
        teachers = [user for user in users if user[3] == 1]
        students_list = "\n".join(
            f"|🆔: {user_id}| |👤: https://t.me/{username}| |Группа: {value}| |🔔: {notify}|"
            for user_id, username, value, _, notify in students
            )
        teachers_list = "\n".join(f"|🆔: {user_id}| |👤: https://t.me/{username}| |ФИО: {value}| |🔔: {notify}|"
            for user_id, username, value, _, notify in teachers
            )
        file.write(
            f"Зарегистрированных пользователей: {count_users}\n\n"
            f"Студенты (всего: {len(students)}):\n{students_list}\n\n"
            f"Преподаватели (всего: {len(teachers)}):\n{teachers_list}")

    # Отправляем файл
    file_from_pc = FSInputFile("users_list.txt")
    await message.answer_document(file_from_pc, caption="Список пользователей")

    # Удаляем временный файл
    os.remove("users_list.txt")

async def send_users_paginated(message: types.Message, users: list, page: int = 0):
    users_per_page = 20
    start = page * users_per_page
    end = start + users_per_page
    users_slice = users[start:end]

    response = "Список пользователей:\n\n"
    for user in users_slice:
        user_id, username, value, is_teacher, notify = user
        role = "Преподаватель" if is_teacher else "Студент"
        response += f"|🆔: {user_id}| |👤: @{username}| |Роль: {role}| |Группа\ФИО: {value}| |🔔: {notify}|\n"

    # Создаем кнопки для навигации
    keyboard_buttons = []
    if page > 0:
        keyboard_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"users_page_{page - 1}"))
    keyboard_buttons.append(InlineKeyboardButton(text="🏠", callback_data="main_menu"))
    if end < len(users):
        keyboard_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"users_page_{page + 1}"))

    # Создаем клавиатуру с кнопками
    keyboard = InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])

    await message.answer(response, reply_markup=keyboard)

async def send_schedule(message: types.Message, days_offset: int, caption: str, send_as_text: bool = False):
    target_date = (date.today() + timedelta(days=days_offset)).strftime("%d.%m.%Y")
    file_name = f'schedule/{target_date}.docx'
    user_id = message.from_user.id
    value, is_teacher, _ = get_user_data(user_id)
    username = message.from_user.username
    if value is None or is_teacher is None:
        if send_as_text:
            await message.answer("Чтобы получать расписание в текстовой форме, зарегистрируйтесь, прописав /login.")
            logging.info(f"Пользователь {username} сделал запрос, будучи не зарегистрированным")
        else:
            if os.path.isfile(file_name):
                file_from_pc = FSInputFile(file_name)
                await message.answer_document(file_from_pc, caption=caption, reply_markup=main_keyboard)
            else:
                await message.answer("Расписания пока еще нет, извините", reply_markup=main_keyboard)
        return  # Завершаем выполнение функции

    try:
        if send_as_text:
            schedule_data, teacher_schedule_data = process_schedule_file(file_name)
            if schedule_data and teacher_schedule_data:
                if is_teacher:
                    if value in teacher_schedule_data:
                        all_entries = []
                        for group, entries in teacher_schedule_data[value].items():
                            for entry in entries.split('\n'):
                                pair_number = int(entry.split('|')[1].split('.')[0])
                                all_entries.append((pair_number, group, entry))

                        all_entries.sort(key=lambda x: x[0])

                        grouped_entries = []
                        current_group = None
                        current_entries = []
                        for pair_number, group, entry in all_entries:
                            if group == current_group:
                                current_entries.append(entry)
                            else:
                                if current_group:
                                    grouped_entries.append((current_group, current_entries))
                                current_group = group
                                current_entries = [entry]
                        if current_group:
                            grouped_entries.append((current_group, current_entries))

                        response = f"Ваше расписание на {target_date}:\n\n|Пара| |Кабинет|\n\n"
                        for group, entries in grouped_entries:
                            response += f"С группой {group}:\n"
                            response += '\n'.join(entries) + '\n\n'

                        await message.answer(response)
                    else:
                        await message.answer("У вас нет пар на этот день.")
                else:
                    if value in schedule_data:
                        await message.answer(
                            f"Расписание для группы {value} на {target_date}:\n\n|Пара| |Преподаватель| |Кабинет|\n\n{schedule_data[value]}")
                    else:
                        await message.answer("Расписание для вашей группы не найдено.")
            else:
                await message.answer("Извините, расписание не удалось обработать.")
        else:
            if os.path.isfile(file_name):
                file_from_pc = FSInputFile(file_name)
                await message.answer_document(file_from_pc, caption=caption, reply_markup=main_keyboard)
            else:
                await message.answer("Расписания пока еще нет, извините", reply_markup=main_keyboard)

    except Exception as e:
        logging.error(f"Ошибка поиска файла: {e}")

async def send_schedule_choose_group(message: types.Message, group_name: str, days_offset: int, caption: str, send_as_text: bool = False):
    target_date = (date.today() + timedelta(days=days_offset)).strftime("%d.%m.%Y")
    file_name = f'schedule/{target_date}.docx'
    username = message.from_user.username
    value, is_teacher, _ = get_user_data(message.from_user.id)
    try:
        if value is None or is_teacher is None:
            if send_as_text:
                schedule_data, teacher_schedule_data = process_schedule_file(file_name)
                if schedule_data and teacher_schedule_data:
                    if group_name in schedule_data:
                        await message.answer(f"Расписание для группы {group_name} на {target_date}:\n\n{schedule_data[group_name]}")
                        logging.info(f"Пользователь {username} сделал запрос, будучи не зарегистрированным")
                    else:
                        await message.answer("Расписание для этой группы не найдено.")
                else:
                    await message.answer("Извините, расписание не удалось обработать.")
            else:
                if os.path.isfile(file_name):
                    file_from_pc = FSInputFile(file_name)
                    await message.answer_document(file_from_pc, caption=caption, reply_markup=main_keyboard)
                else:
                    await message.answer("Расписания пока еще нет, извините", reply_markup=main_keyboard)
            return
        if send_as_text:
            schedule_data, teacher_schedule_data = process_schedule_file(file_name)
            if schedule_data and teacher_schedule_data:
                if group_name in schedule_data:
                    await message.answer(
                    f"Расписание для группы {group_name} на {target_date}:\n\n{schedule_data[group_name]}")
                    await offer_to_add_favorite_group(message, group_name)
                else:
                    await message.answer("Расписание для этой группы не найдено.")
            else:
                await message.answer("Извините, расписание не удалось обработать.")
        else:
            if os.path.isfile(file_name):
                file_from_pc = FSInputFile(file_name)
                await message.answer_document(file_from_pc, caption=caption, reply_markup=main_keyboard)
            else:
                await message.answer("Расписания пока еще нет, извините", reply_markup=main_keyboard)

    except Exception as e:
        logging.error(f"Ошибка поиска файла: {e}")

async def offer_to_add_favorite_group(message: types.Message, group_name: str):
    user_id = message.from_user.id
    favorite_groups = get_favorite_groups(user_id)

    if group_name in favorite_groups:
        # Группа уже в избранных, ничего не предлагаем
        return

    # Создаем inline-клавиатуру с кнопками "Да" и "Нет"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data=f"add_favorite_{group_name}")],
        [InlineKeyboardButton(text="Нет", callback_data="cancel_favorite")]
    ])

    await message.answer(f"Хотите добавить группу {group_name} в избранные?", reply_markup=keyboard)

async def send_as_text2(message: types.Message, file_name):
    target_date = message.text
    user_id = message.from_user.id
    username = message.from_user.username
    schedule_data, teacher_schedule_data = process_schedule_file(file_name)
    if schedule_data and teacher_schedule_data:
        value, is_teacher, _ = get_user_data(user_id)

        if value is None or is_teacher is None:
            await message.answer("Чтобы получать расписание в текстовой форме, зарегистрируйтесь, написав /login.")
            logging.info(f"Пользователь {username} сделал запрос, будучи не зарегистрированным")
            return

        if is_teacher:
            if value in teacher_schedule_data:
                all_entries = []
                for group, entries in teacher_schedule_data[value].items():
                    for entry in entries.split('\n'):
                        pair_number = int(entry.split('|')[1].split('.')[0])
                        all_entries.append((pair_number, group, entry))

                all_entries.sort(key=lambda x: x[0])

                grouped_entries = []
                current_group = None
                current_entries = []
                for pair_number, group, entry in all_entries:
                    if group == current_group:
                        current_entries.append(entry)
                    else:
                        if current_group:
                            grouped_entries.append((current_group, current_entries))
                        current_group = group
                        current_entries = [entry]
                if current_group:
                    grouped_entries.append((current_group, current_entries))

                response = f"Ваше расписание на {target_date}:\n\n |Пара| |Кабинет|\n\n"
                for group, entries in grouped_entries:
                    response += f"С группой {group}:\n"
                    response += '\n'.join(entries) + '\n\n'

                await message.answer(response)
            else:
                await message.answer("Судя по файлу, у вас нет пар на этот день. Возможно, произошла ошибка.")
        else:
            if value in schedule_data:
                await message.answer(
                    f"Расписание для группы {value} на {target_date}:\n\n|Пара| |Преподаватель| |Кабинет|\n\n{schedule_data[value]}")
            else:
                await message.answer("Расписание для вашей группы не найдено.")
    else:
        await message.answer("Извините, расписание не удалось обработать.")

async def send_as_text_for_another_group(message: types.Message, file_name, group_name):
    target_date = message.text
    user_id = message.from_user.id
    username = message.from_user.username
    schedule_data, teacher_schedule_data = process_schedule_file(file_name)
    value = group_name
    if schedule_data and teacher_schedule_data:
        _ , is_teacher, _ = get_user_data(user_id)

        if value is None or is_teacher is None:
            await message.answer("Чтобы получать расписание в текстовой форме, зарегистрируйтесь, написав /login.")
            logging.info(f"Пользователь {username} сделал запрос, будучи не зарегистрированным")
            return

        if is_teacher:
            if value in teacher_schedule_data:
                all_entries = []
                for group, entries in teacher_schedule_data[value].items():
                    for entry in entries.split('\n'):
                        pair_number = int(entry.split('|')[1].split('.')[0])
                        all_entries.append((pair_number, group, entry))

                all_entries.sort(key=lambda x: x[0])

                grouped_entries = []
                current_group = None
                current_entries = []
                for pair_number, group, entry in all_entries:
                    if group == current_group:
                        current_entries.append(entry)
                    else:
                        if current_group:
                            grouped_entries.append((current_group, current_entries))
                        current_group = group
                        current_entries = [entry]
                if current_group:
                    grouped_entries.append((current_group, current_entries))

                response = f"Ваше расписание на {target_date}:\n\n |Пара| |Кабинет|\n\n"
                for group, entries in grouped_entries:
                    response += f"С группой {group}:\n"
                    response += '\n'.join(entries) + '\n\n'

                await message.answer(response)
            else:
                await message.answer("Судя по файлу, у вас нет пар на этот день. Возможно, произошла ошибка.")
        else:
            if value in schedule_data:
                await message.answer(
                    f"Расписание для группы {value} на {target_date}:\n\n|Пара| |Преподаватель| |Кабинет|\n\n{schedule_data[value]}")
            else:
                await message.answer("Расписание для вашей группы не найдено.")
    else:
        await message.answer("Извините, расписание не удалось обработать.")

async def send_notification(chat_id, message):
    await bot.send_message(chat_id, message)


async def download_other_date(date: str):
    target_date = date
    filename = f"Расписание {target_date}.docx"
    root_directory = "/ДТК/Расписание занятий/"

    def find_file_sync(yadisk, directory, filename):
        for item in yadisk.listdir(directory):
            if item['type'] == 'dir':
                found_file = find_file_sync(yadisk, item['path'], filename)
                if found_file:
                    return found_file
            elif item['name'] == filename:
                return item['path']
        return None

    def download_file_sync(file_path, local_path):
        yadisk_client.download(file_path, local_path)

    try:
        file_path = await asyncio.to_thread(find_file_sync, yadisk_client, root_directory, filename)
        if file_path:
            local_path = f"schedule/{target_date}.docx"
            await asyncio.to_thread(download_file_sync, file_path, local_path)
            logging.info(f"Файл на {target_date} скачен из {file_path}")
            return True  # Файл успешно скачан
        else:
            logging.warning(f"Файла на {target_date} нет")
            return False  # Файл не найден
    except Exception as e:
        logging.error(f"Ошибка при скачивании файла на {target_date}: {e}")
        return False  # Произошла ошибка


async def download_schedule(days_offset: int):
    target_date = (date.today() + timedelta(days=days_offset)).strftime("%d.%m.%Y")
    filename = f"Расписание {target_date}.docx"
    root_directory = "/ДТК/Расписание занятий/"
    local_path = f"schedule/{target_date}.docx"

    def find_file_sync(yadisk, directory, filename):
        for item in yadisk.listdir(directory):
            if item['type'] == 'dir':
                found_file = find_file_sync(yadisk, item['path'], filename)
                if found_file:
                    return found_file
            elif item['name'] == filename:
                return item['path']
        return None

    def download_file_sync(file_path, local_path):
        yadisk_client.download(file_path, local_path)

    # Получаем текущий хеш (если файл существует)
    old_hash = None
    if os.path.exists(local_path):
        old_hash = get_file_hash(local_path)

    try:
        file_path = await asyncio.to_thread(find_file_sync, yadisk_client, root_directory, filename)
        if file_path:
            local_path = f"schedule/{target_date}.docx"
            await asyncio.to_thread(download_file_sync, file_path, local_path)
            new_hash = get_file_hash(local_path)
            if old_hash and new_hash != old_hash:
                logging.info(f"Расписание на {target_date} изменилось и было загружено на сервер")
                # Удаляем старый кеш, если он есть
                cache_key = f"{target_date}.docx"
                if cache_key in schedule_cache:
                    del schedule_cache[cache_key]
                    logging.info(f"Кеш для {target_date} очищен перед обновлением")
                await check_and_notify(filename, update=True)
            elif not old_hash:
                logging.info(f"Расписание на {target_date} загружено")
                check_and_notify(filename)
        else:
            logging.warning(f"Файла на {target_date} нет")
    except Exception as e:
        logging.error(f"Ошибка при скачивании файла на {target_date}: {e}")


async def send_schedule_to_all_users(days_offset: int, caption: str):
    users = get_all_users_data()
    if not users:
        logging.warning("Нет пользователей для рассылки расписания.")
        return

    target_date = (date.today() + timedelta(days=days_offset)).strftime("%d.%m.%Y")
    file_name = f'schedule/{target_date}.docx'

    if not os.path.isfile(file_name):
        logging.warning(f"Файл расписания на {target_date} не найден.")
        return

        # Получаем данные из кеша (будет автоматически обновлён при необходимости)
    cache_result = process_schedule_file(file_name)
    if not cache_result:
        return

    schedule_data, teacher_schedule_data = cache_result["data"]
    day_text = "на сегодня" if days_offset == 0 else "на завтра"

    for user_id, username, value, is_teacher, notifications_enabled in users:
        if notifications_enabled == 1:
            try:
                # Отправляем файл с расписанием
                file_from_pc = FSInputFile(file_name)
                await bot.send_document(user_id, file_from_pc, caption=caption)

                # Обрабатываем расписание для текстового вывода
                schedule_data, teacher_schedule_data = process_schedule_file(file_name)
                if is_teacher:
                    if value in teacher_schedule_data:
                        # Форматируем расписание для преподавателя
                        all_entries = []
                        for group, entries in teacher_schedule_data[value].items():
                            for entry in entries.split("\n"):
                                pair_number = entry.split("|")[1].split(".")[0].strip()  # Извлекаем номер пары
                                all_entries.append((int(pair_number), group, entry))

                        # Сортируем все пары по номеру
                        all_entries.sort(key=lambda x: x[0])

                        # Группируем подряд идущие пары для одной группы, если они идут одновременно
                        grouped_entries = []
                        current_group = None
                        current_entries = []
                        for pair_number, group, entry in all_entries:
                            if group == current_group:
                                # Если группа совпадает с предыдущей, добавляем запись в текущий блок
                                current_entries.append(entry)
                            else:
                                # Если группа другая, создаём новый блок
                                if current_group:
                                    grouped_entries.append((current_group, current_entries))
                                current_group = group
                                current_entries = [entry]
                        if current_group:
                            grouped_entries.append((current_group, current_entries))

                    # Формируем итоговый ответ
                        response = f"Ваше расписание {day_text}:\n\n |Пара| |Кабинет|\n\n"
                        for group, entries in grouped_entries:
                            response += f"С группой {group}:\n"
                            response += "\n".join(entries) + "\n\n"

                        await bot.send_message(user_id, response)
                    else:
                        await bot.send_message(user_id, "Возможно у вас нет пар на этот день. Возможно, произошла ошибка")
                else:
                    if value in schedule_data:
                        await bot.send_message(user_id,
                                           f"Расписание для группы {value} {day_text}:\n\n{schedule_data[value]}")
                    else:
                        await bot.send_message(user_id, "Расписание для вашей группы не найдено.")
            except Exception as e:
                logging.error(f"Не удалось отправить расписание пользователю {user_id}: {e}")
        else:
            continue

async def favorite_groups_show(message: types.Message, cancle: bool = False):
    user_id = message.from_user.id
    keyboard = create_favorite_groups_keyboard(user_id)
    if not cancle:
        sent_message = await message.answer(
            "Загружаю избранные группы...",
            reply_markup=ReplyKeyboardRemove()
        )
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=sent_message.message_id)
    # Затем редактируем ЭТО ЖЕ сообщение, добавляя inline-клавиатуру
    await message.answer(
        "Ваши избранные группы:",
        reply_markup=keyboard
    )
    del user_states["profile_edit"][user_id]

async def morning_schedule_task():
    await send_schedule_to_all_users(days_offset=0, caption="Расписание на сегодня")


async def evening_schedule_task():
    await send_schedule_to_all_users(days_offset=1, caption="Расписание на завтра")

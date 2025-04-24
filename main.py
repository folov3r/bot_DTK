import asyncio
import logging
import types
from aiogram.enums import ParseMode
from aiogram.filters.command import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import F
from click.formatting import measure_table
from all_texts import admin_comm
from all_texts import help_message, start_message, text_log, zvon_schedule
from other_def import *

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_TEST")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("log/log.txt", encoding='utf-8-sig'),
        logging.StreamHandler()
    ]
)

logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


yadisk_client = yadisk.Client(token=YANDEX_TOKEN)

if yadisk_client.check_token():
    logging.info("Valid API Yandex? True")
else:
    logging.info("Valid API Yandex? False")

logging.getLogger("yadisk").setLevel(logging.WARNING)

ROLE_ADMIN = 1
ROLE_SECONDARY_ADMIN = 2
ROLE_MAIN_ADMIN = 3


# Декоратор для проверки роли администрации
def has_role(required_role: int):
    def decorator(func):
        async def wrapper(message: types.Message, *args, **kwargs):
            user_id = message.from_user.id
            user_role = get_admin_role(user_id)
            if user_role >= required_role:
                return await func(message, *args, **kwargs)
            await message.answer("У вас недостаточно прав для выполнения этой команды.")

        return wrapper

    return decorator


# добавление администратора
@dp.message(Command("add_admin"))
@has_role(ROLE_SECONDARY_ADMIN)
async def set_role(message: types.Message, **kwargs):
    try:
        _, user_id, username, role = message.text.split()
        user_id = int(user_id)
        role = int(role)
        username = str(username)

        role_admin = get_admin_role(message.from_user.id)
        if role_admin >= role:
            if role not in [ROLE_ADMIN, ROLE_SECONDARY_ADMIN, ROLE_MAIN_ADMIN]:
                await message.answer("Недопустимая роль уровня доступа.")
                return
            add_admin(user_id, username, role, message.from_user.username)
            logging.warning(
                f"Пользователь {message.from_user.username} назначил пользователя {username} администратором с уровнем доступа {role}")
            await message.answer(f"✅ Уровень доступа {role} для пользователя {username} назначена успешно.")
        else:
            await message.answer(
                f"❌ Вы не можете назначить пользователя на роль администратора с уровнем доступа {role} из соображения безопасности")
            logging.warning(
                f"Пользователь {message.from_user.username} попытался назначить пользователя {username} администратором с уровнем доступа {role}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# Удаление администратора
@dp.message(Command("remove_admin"))
@has_role(ROLE_SECONDARY_ADMIN)
async def remove_admin(message: types.Message, **kwargs):
    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
        admin_role = get_admin_role(message.from_user.id)
        remove_admin_role = get_admin_role(user_id)
        username_remove_admin = get_username_admin(user_id)
        if admin_role >= remove_admin_role:
            remove_admin_def(user_id)
            logging.warning(
                f"Пользователь {message.from_user.username} отозвал права доступа у пользователя {username_remove_admin}")
            await message.answer(f"✅ Пользователь {username_remove_admin} больше не администратор.")
        else:
            logging.warning(
                f"Пользователь {message.from_user.username} попытался удалить администратора {username_remove_admin}")
            await message.answer(
                f"❌ Вы не можете удалить данного администратора, так как его уровень доступа выше вашего")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# Отправка списка администраторов
@dp.message(Command("list_admins"))
@has_role(ROLE_ADMIN)
async def list_admins(message: types.Message, **kwargs):
    admins = get_all_admins()
    if not admins:
        await message.answer("Администраторы не найдены.")
        return
    admins_list = "\n".join(
        [f"|🆔: {user_id}| |@ : {username}| |status: {role}| |who add: @{who_add}|" for user_id, username, role, who_add in admins])
    await message.answer(f"Список администраторов:\n{admins_list}")


# Функция авто рассылки сообщения для всех пользователей в дб users
@dp.message(Command("broadcast"))
@has_role(ROLE_SECONDARY_ADMIN)
async def broadcast_message(message: types.Message, **kwargs):
    try:
        text_to_send = message.text.split(maxsplit=1)[1]
    except IndexError:
        await message.answer("Используйте команду в формате: /broadcast <текст сообщения>")
        return

    users = get_all_users_id()
    if not users:
        await message.answer("В базе данных нет пользователей.")
        return

    success_count = 0
    failed_count = 0

    for user_id in users:
        try:
            await bot.send_message(user_id, text_to_send)
            success_count += 1
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            failed_count += 1

    await message.answer(
        f"Сообщение отправлено:\n"
        f"✅ Успешно: {success_count}\n"
        f"❌ Не удалось: {failed_count}"
    )


# Получение списка пользователей
@dp.message(Command("list_users"))
@has_role(ROLE_SECONDARY_ADMIN)
async def list_users_1(message: types.Message, **kwargs):
    users = get_all_users_data()

    if not users:
        await message.answer("В базе данных нет пользователей.")
        return
    else:
        await save_list_users(message, users)
        await message.answer(f"Всего пользователей: {len(users)}\n Список каких пользователей вы хотите просмотреть?", reply_markup=choose_list_users)
        user_states["list_users"][message.from_user.id] = message.from_user.username

@dp.message(lambda message: message.from_user.id in user_states["list_users"])
async def list_users(message: types.Message, **kwargs):
    users = get_all_users_data()

    if not users:
        await message.answer("В базе данных нет пользователей.")
        return

    count_users = len(users)
    students = [user for user in users if user[3] == 0]
    teachers = [user for user in users if user[3] == 1]

    students_list = "\n".join(
        f"|🆔: {user_id}| |👤: @{username}| |Группа: {value}| |🔔: {notifications_enabled}|"
        for user_id, username, value, _, notifications_enabled in students
    )

    teachers_list = "\n".join(
        f"|🆔: {user_id}| |👤: @{username}| |ФИО: {value}| |🔔: {notifications_enabled}|"
        for user_id, username, value, _, notifications_enabled in teachers
    )
    if message.text == "Студентов":
        await send_users_paginated(message, students, page=0)
        del user_states["list_users"][message.from_user.id]
    elif message.text == "Преподавателей":
        await send_users_paginated(message, teachers, page=0)
        del user_states["list_users"][message.from_user.id]
    await message.answer(
        f"Зарегистрированных пользователей: {count_users}\n\n"
        f"Студенты (всего: {len(students)}):\n{students_list}\n\n"
        f"Преподаватели (всего: {len(teachers)}):\n{teachers_list}"
    )

@dp.callback_query(lambda c: c.data.startswith("users_page_"))
async def process_users_pagination(callback_query: types.CallbackQuery):
    page = int(callback_query.data.split("_")[-1])
    users = get_all_users_data()
    await send_users_paginated(callback_query.message, users, page)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("main_menu"))
async def go_main_menu(callback_query: types.CallbackQuery):
    await callback_query.message.delete()  # Удаляем текущее сообщение
    await callback_query.message.answer("Главное меню:", reply_markup=main_keyboard)
    await callback_query.answer()  # Ответ на callback-запрос

# Получение логов в виде txt файла
@dp.message(Command("logs_txt"))
@has_role(ROLE_SECONDARY_ADMIN)
async def send_logs(message: types.Message, **kwargs):
    file_name = 'log/log.txt'
    file_from_pc = FSInputFile(file_name)
    await message.answer_document(file_from_pc)


# Список команд для администрации
@dp.message(Command("admin"))
@has_role(ROLE_ADMIN)
async def send_admin_commands(message: types.Message, **kwargs):
    await message.answer(admin_comm)


add_admin(6142823280, "@folov3r", ROLE_MAIN_ADMIN, "folov3r")


@dp.message(Command("login"))
async def login(message: types.Message, **kwargs):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"

    user_states["login"][user_id] = username

    role_keyboard = create_keyboard([["Студент", "Преподаватель"]])
    await message.answer("Кто вы?\nСтудент или преподаватель?", reply_markup=role_keyboard)


# Получение role от пользователя
@dp.message(lambda message: message.from_user.id in user_states["login"])
async def ask_for_value(message: types.Message, **kwargs):
    user_id = message.from_user.id
    role = message.text

    if role == "Студент":
        await message.answer(
            "Пожалуйста, введите группу, расписания которой хотите получать.\nЖелательно указывать группу правильно, соблюдая регистр и правильность написания.\nНапример:\n✅ ОП-2 ✅\n❌ оп 2; Оп2; оП-2 ❌",
            reply_markup=return_keyboard)
        user_states["chose_role"][user_id] = role
        del user_states["login"][user_id]
    elif role == "Преподаватель":
        await message.answer("Пожалуйста, введите ваше ФИО (например, Иванов И.И.).", reply_markup=return_keyboard)
        user_states["chose_role"][user_id] = role
        del user_states["login"][user_id]
    else:
        await message.answer("Пожалуйста, используйте на экранные кнопки")
        return


# Сохранение value и role для пользователя при login
@dp.message(lambda message: message.from_user.id in user_states["chose_role"])
async def save_inform(message: types.Message, **kwargs):
    user_id = message.from_user.id
    value = message.text
    role = user_states["chose_role"][user_id]
    username = message.from_user.username
    if value == "Вернуться":
        del user_states["chose_role"][user_id]
        await login(message)
    else:
        if role == "Студент":
            validated_group, is_valid = validate_and_correct_group(value)
            if is_valid:
                save_user_data(user_id, message.from_user.username, validated_group, is_teacher=0)
                await message.reply(
                    f"Вы успешно зарегистрировались. Вы будете получать расписание для группы {validated_group}.",
                    reply_markup=main_keyboard)
                del user_states["chose_role"][user_id]
                logging.info(f"Пользователь {username} зарегистрировался как студент, поприветствуем!")
            else:
                await message.answer("Некорректный номер группы. Пожалуйста, введите номер группы снова.")
                return
        elif role == "Преподаватель":
            save_user_data(user_id, message.from_user.username, value, is_teacher=1)
            await message.reply(
                f"Вы успешно зарегистрировались. Вы будете получать расписание для преподавателя {value}",
                reply_markup=main_keyboard)
            del user_states["chose_role"][user_id]
            logging.info(f"Пользователь {username} зарегистрировался как преподаватель, поприветствуем!")


# Обработка запроса на получение профиля для пользователя
@dp.message(F.text == "Профиль")
async def profile(message: types.Message, **kwargs):
    user_id = message.from_user.id
    value, is_teacher, notification_enabled = get_user_data(user_id)
    username = message.from_user.username
    if value is None or is_teacher is None:
        await message.answer("Вас нет в базе данных. Пожалуйста, зарегистрируйтесь, прописав /login.")
        logging.info(f"Пользователь {username} сделал запрос, будучи не зарегистрированным")
        return  # Завершаем выполнение функции

    if notification_enabled == 1:
        notification_enabled = 'Включена'
    else:
        notification_enabled = "Выключена"

    if is_teacher == 0:
        is_teacher = "Студент"
    else:
        is_teacher = "Преподаватель"
    sent_message = await message.answer(f"""Ваш профиль:
👤Ваш юз: @{message.from_user.username}
👥Роль: {is_teacher}
❓Расписание кого отслеживаете: {value}
📩Авто рассылка: {notification_enabled}""", reply_markup=profile_keyboard)
    user_states["profile_edit"][user_id] = user_id
    profile_messages[user_id] = sent_message.message_id


# Обработка функций системы профиля
@dp.message(lambda message: message.from_user.id in user_states["profile_edit"])
async def edit_profile_user(message: types.Message, **kwargs):
    text_message = message.text
    user_id = message.from_user.id
    value, is_teacher, notifications_enabled = get_user_data(user_id)
    username = message.from_user.username
    if text_message == "Изменить данные":
        remove_user_def(user_id)
        del user_states["profile_edit"][user_id]
        await login(message)
    elif text_message == "Удалить аккаунт":
        username = message.from_user.username
        user_states["delete_user"][user_id] = username
        await message.answer('Вы уверены, что хотите перестать получать расписание?', reply_markup=yes_no_keyboard)
        del user_states["profile_edit"][user_id]
    elif text_message == "Авто рассылка":
        if notifications_enabled == 1:
            user_id = message.from_user.id
            disable_notify(user_id)
            await message.answer("🔕Уведомления отключены🔕")
        else:
            user_id = message.from_user.id
            enable_notify(user_id)
            await message.answer("🔔Уведомления включены🔔")
        if user_id in profile_messages:
            try:
                await bot.delete_message(chat_id=user_id, message_id=profile_messages[user_id])
                del profile_messages[user_id]
            except Exception as e:
                logging.error(f"Ошибка удаления сообщения профиля: {e}")
        await profile(message)
    elif text_message == "Обратная связь":
        del user_states["profile_edit"][user_id]
        await message.answer(
            "Напишите отзыв или жалобу по поводу работы бота, мы его отправим главному администратору:",
            reply_markup=back_feedback_keyboard)
        user_states["feedback"][user_id] = username
    elif text_message == "Избранные группы":
        await favorite_groups_show(message)
    elif text_message == "Вернуться":
        await message.answer("Главное меню:", reply_markup=main_keyboard)
        del user_states["profile_edit"][user_id]
    else:
        await message.answer("Пожалуйста, используйте кнопки, которые вы видите на экране",reply_markup=profile_keyboard)
    try:
        await bot.delete_message(chat_id=user_id, message_id=message.message_id)
    except Exception as e:
        logging.error(f"Ошибка удаления сообщения пользователя: {e}")

@dp.callback_query(lambda c: c.data.startswith("remove_favorite_"))
async def handle_remove_favorite(callback_query: types.CallbackQuery):
    group_name = callback_query.data.split("_")[-1]
    user_id = callback_query.from_user.id

    # Удаляем группу из избранных
    remove_favorite_group(user_id, group_name)
    await callback_query.answer(f"Группа {group_name} удалена из избранных.")
    await callback_query.message.edit_reply_markup(reply_markup=create_favorite_groups_keyboard(user_id))

@dp.callback_query(lambda c: c.data == "add_favorite_group")
async def handle_add_favorite_group(callback_query: types.CallbackQuery):
    await callback_query.message.answer("Введите название группы для добавления в избранные:", reply_markup=cancel_keyboard)
    user_states["add_favorite_group"][callback_query.from_user.id] = callback_query.from_user.username
    try:
        await bot.delete_message(chat_id=callback_query.from_user.id, message_id=callback_query.message.message_id)
    except Exception as e:
        logging.error(f"Ошибка удаления сообщения пользователя: {e}")
    await callback_query.answer()

@dp.message(lambda message: message.from_user.id in user_states["add_favorite_group"])
async def handle_add_favorite_group_input(message: types.Message):
    group_name = message.text
    user_id = message.from_user.id

    if group_name == "Отмена":
        await message.answer("Действие отменено")
        await favorite_groups_show(message, cancle = True)
        del user_states["add_favorite_group"][user_id]
        return
    else:
        validated_group, is_valid = validate_and_correct_group(group_name)
        if is_valid:
            # Добавляем группу в избранные
            group_name = validated_group
            add_favorite_group(user_id, group_name)
            await message.answer(f"Группа {group_name} добавлена в избранные.", reply_markup=main_keyboard)
            del user_states["add_favorite_group"][user_id]
        else:
            await message.answer("Введена несуществующая группа. пожалуйста, перепроверьте и введите правильно написанную группу")
            return

@dp.callback_query(lambda c: c.data == "back_to_profile")
async def back_to_profile_def(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    user_id = callback_query.from_user.id
    value, is_teacher, notification_enabled = get_user_data(user_id)
    username = callback_query.from_user.username
    if value is None or is_teacher is None:
        await callback_query.message.answer("Вас нет в базе данных. Пожалуйста, зарегистрируйтесь, прописав /login.")
        logging.info(f"Пользователь {username} сделал запрос, будучи не зарегистрированным")
        return  # Завершаем выполнение функции

    if notification_enabled == 1:
        notification_enabled = 'Включена'
    else:
        notification_enabled = "Выключена"

    if is_teacher == 0:
        is_teacher = "Студент"
    else:
        is_teacher = "Преподаватель"
    sent_message = await callback_query.message.answer(f"""Ваш профиль:
👤Ваш юз: @{username}
👥Роль: {is_teacher}
❓Расписание кого отслеживаете: {value}
📩Авто рассылка: {notification_enabled}""", reply_markup=profile_keyboard)
    user_states["profile_edit"][user_id] = user_id
    profile_messages[user_id] = sent_message.message_id
    await callback_query.answer()


# Обработка отправки отзыва глав админу (указан id глав админа folov3r, на данный момент)
@dp.message(lambda message: message.from_user.id in user_states["feedback"])
async def process_feedback(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    feedback = message.text
    if feedback == "Вернуться на главную":
        del user_states["feedback"][user_id]
        await message.answer("Главная:", reply_markup=main_keyboard)
    else:
        await bot.send_message(chat_id=6142823280, text=f"Обратная связь от @{username}:\n\n{feedback}")
        await message.answer("Спасибо за обратную связь!", reply_markup=main_keyboard)
        del user_states["feedback"][user_id]


# Обработка запроса на удаление данных из бд
@dp.message(lambda message: message.from_user.id in user_states["delete_user"])
async def delete_conf_def(message: types.Message, **kwargs):
    text = message.text
    user_id = message.from_user.id
    if text == 'Да':
        remove_user_def(user_id)
        await message.answer(
            '✅ Вы успешно удалили себя из системы.\nЕсли захотите вернуться, то вы можете повторно зарегистрироваться, нажав кнопку ниже или прописав /login, а также перезапустив бота.\nУдачи, до скорого 👋',
            reply_markup=login_lvl_1_keyboard)
    else:
        await message.answer('Спасибо, что вы остались!', reply_markup=main_keyboard)

    del user_states["delete_user"][user_id]


@dp.message(Command("start"))
async def cmd_start(message: types.Message, **kwargs):
    check_id = get_all_users_id()
    if message.from_user.id in check_id:
        await message.answer(start_message, reply_markup=main_keyboard, parse_mode=ParseMode.HTML)
    else:
        await message.answer(start_message, parse_mode=ParseMode.HTML)
        await message.answer(
            "Вас нет в базе для получения расписания. Чтобы работать с ботом, вам нужно пройти процесс регистрации.\nПожалуйста, нажмите кнопку снизу или напишите /login ",
            reply_markup=login_lvl_1_keyboard)


# Вызов списка команд для пользователей
@dp.message(Command("help"))
async def cmd_help(message: types.Message, **kwargs):
    await message.answer(help_message)


# "пасхалка"
@dp.message(F.text == "Lain")
async def egg_lain(message: types.Message, **kwargs):
    image_from_pc = FSInputFile("lain.jpg")
    await message.answer_photo(image_from_pc)
    await message.answer("No matter where you are. Everyone is always connected")


# "пасхалка"
@dp.message(F.text == 'Me')
async def egg_me(message: types.Message):
    await message.answer("everything for everyone")


# /change - лог изменений в боте (для пользователей, текст заполняется в all_texts)
@dp.message(Command("change"))
async def send_change_logs(message: types.Message, **kwargs):
    await message.reply(text_log, parse_mode=ParseMode.HTML)


# Получение ботом запроса для получения расписания пользователем на интересующий день
@dp.message(F.text == "Проверить расписание")
async def check_schedule(message: types.Message, **kwargs):
    username = message.from_user.username
    user_id = message.from_user.id
    user_states["check_schedule"][user_id] = username
    await message.reply("Расписание на:", reply_markup=schedule_keyboard)


# Функция обработки запроса получения расписания
@dp.message(lambda message: message.from_user.id in user_states["check_schedule"])
async def check_schedule1(message: types.Message, **kwargs):
    username = message.from_user.username
    user_id = message.from_user.id
    text = message.text
    if text == "Сегодня":
        del user_states["check_schedule"][user_id]
        await send_schedule(message, days_offset=0, caption="Расписание на сегодня")
        await send_schedule(message, days_offset=0, caption="Расписание на сегодня", send_as_text=True)
    elif text == "Завтра":
        del user_states["check_schedule"][user_id]
        await send_schedule(message, days_offset=1, caption="Расписание на завтра")
        await send_schedule(message, days_offset=1, caption="Расписание на завтра", send_as_text=True)
    elif text == "После завтра":
        del user_states["check_schedule"][user_id]
        await send_schedule(message, days_offset=2, caption="Расписание на после завтра")
        await send_schedule(message, days_offset=2, caption="Расписание на после завтра", send_as_text=True)
    elif text == "Другая дата":
        del user_states["check_schedule"][user_id]
        user_states["other_date"][user_id] = username
        await message.answer("Пришлите дату в формате дд.мм.гггг", reply_markup=cancel_keyboard)
    elif text == "Другая группа":
        del user_states["check_schedule"][user_id]
        user_states["check_another_group"][user_id] = username
        await message.answer("Напишите группу, для которой вы хотите просмотреть расписание", reply_markup=return_keyboard)
    elif text == "Отмена":
        del user_states["check_schedule"][user_id]
        await message.answer("Действие отменено", reply_markup=main_keyboard)
    else:
        await message.answer("Пожалуйста, используйте на экранные кнопки")

@dp.message(lambda message: message.from_user.id in user_states["check_another_group"])
async def check_schedule_another_group(message: types.Message):
    user_id = message.from_user.id
    user_input = message.text
    if user_input == "Вернуться":
        del user_states["check_another_group"][user_id]
        await message.answer("Действие отменено")
        await message.answer("Расписание на:", reply_markup=schedule_keyboard)
        user_states["check_schedule"][user_id] = message.from_user.username
    else:
        validated_group, is_valid = validate_and_correct_group(user_input)
        if is_valid:
            await message.answer('Выберите дату', reply_markup=schedule_keyboard_another_group)
            user_states["set_group_num"][user_id] = validated_group
            del user_states["check_another_group"][user_id]
            logging.info(f"{user_states["set_group_num"].get(user_id)}")
        else:
            await message.answer("Некорректный номер группы. Пожалуйста, введите номер группы снова.")
            return

@dp.message(lambda message: message.from_user.id in user_states["set_group_num"])
async def send_schedule_another_group(message: types.Message):
    user_id = message.from_user.id
    group_name = user_states["set_group_num"].get(user_id)
    text = message.text
    if text == "Сегодня":
        del user_states["set_group_num"][user_id]
        await send_schedule_choose_group(message, group_name=group_name, days_offset=0, caption="Расписание на сегодня")
        await send_schedule_choose_group(message, group_name=group_name, days_offset=0, caption="Расписание на сегодня", send_as_text=True)
    elif text == "Завтра":
        del user_states["set_group_num"][user_id]
        await send_schedule_choose_group(message, group_name=group_name, days_offset=1, caption="Расписание на завтра")
        await send_schedule_choose_group(message, group_name=group_name, days_offset=1, caption="Расписание на завтра", send_as_text=True)
    elif text == "После завтра":
        del user_states["set_group_num"][user_id]
        await send_schedule_choose_group(message, group_name=group_name, days_offset=2, caption="Расписание на после завтра")
        await send_schedule_choose_group(message, group_name=group_name, days_offset=2, caption="Расписание на после завтра", send_as_text=True)
    elif text == "Другая дата":
        del user_states["set_group_num"][user_id]
        user_states["other_date_another_group"][user_id] = group_name
        await message.answer("Пришлите дату в формате дд.мм.гггг", reply_markup=cancel_keyboard)
    elif text == "Вернуться":
        del user_states["set_group_num"][user_id]
        await message.answer("Действие отменено")
        await message.answer("Расписание на:", reply_markup=schedule_keyboard)
        user_states["check_schedule"][user_id] = message.from_user.username
    else:
        await message.answer("Пожалуйста, используйте на экранные кнопки")
        return

@dp.message(lambda message: message.from_user.id in user_states["other_date_another_group"])
async def check_other_date_for_another_group(message: types.Message, **kwargs):
    user_id = message.from_user.id
    text = message.text
    file_name = f'schedule/{text}.docx'
    group_name = user_states["other_date_another_group"].get(user_id)
    if text == "Отмена":
        await message.answer("Действие отменено", reply_markup=main_keyboard)
        del user_states["other_date_another_group"][user_id]
        return

    await message.answer("🔎Производится поиск расписания, ожидайте...")

    if not os.path.isfile(file_name):
        # Если файла нет, пытаемся скачать его с диска
        success = await download_other_date(text)
        if not success:
            await message.answer("Вы ввели неправильные данные, либо расписания нет, извините", reply_markup=main_keyboard)
            del user_states["other_date"][user_id]
            return

    if os.path.isfile(file_name):
        try:
            file_from_pc = FSInputFile(file_name)
            await message.answer_document(file_from_pc, caption=f"Расписание на {text}", reply_markup=main_keyboard)
            await send_as_text_for_another_group(message, file_name, group_name)
        except Exception as e:
            logging.error(f"Ошибка при отправке файла: {e}")
            await message.answer("Произошла ошибка при отправке расписания.", reply_markup=main_keyboard)
    else:
        await message.answer("Расписание не найдено, извините.", reply_markup=main_keyboard)

    del user_states["other_date_another_group"][user_id]

@dp.callback_query(lambda c: c.data.startswith("add_favorite_"))
async def handle_add_favorite(callback_query: types.CallbackQuery):
    group_name = callback_query.data.split("_")[-1]
    user_id = callback_query.from_user.id

    # Добавляем группу в избранные
    add_favorite_group(user_id, group_name)
    await callback_query.answer(f"Группа {group_name} добавлена в избранные.")
    await callback_query.message.edit_reply_markup()  # Убираем клавиатуру

@dp.callback_query(lambda c: c.data == "cancel_favorite")
async def handle_cancel_favorite(callback_query: types.CallbackQuery):
    await callback_query.answer("Группа не добавлена в избранные.")
    await callback_query.message.edit_reply_markup()  # Убираем клавиатуру

# Отправка расписания звонков
@dp.message(F.text == "Расписание звонков")
async def schedule_zvon(message: types.Message, **kwargs):
    await message.answer(f"Расписание звонков:\n\n{zvon_schedule}")


@dp.message(lambda message: message.from_user.id in user_states["check_schedule"])
async def check_schedule_another_group(message: types.Message):
    user_states["set_group_num"][message.from_user.id] = message.text


# Функция отправки расписания на интересующую дату пользователя
@dp.message(lambda message: message.from_user.id in user_states["other_date"])
async def other_data_send(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    file_name = f'schedule/{text}.docx'

    if text == "Отмена":
        await message.answer("Действие отменено", reply_markup=main_keyboard)
        del user_states["other_date"][user_id]
        return

    await message.answer("🔎Производится поиск расписания, ожидайте...")

    # Проверяем, существует ли файл на сервере
    if not os.path.isfile(file_name):
        # Если файла нет, пытаемся скачать его с диска
        success = await download_other_date(text)
        if not success:
            await message.answer("Вы ввели неправильные данные, либо расписания нет, извините", reply_markup=main_keyboard)
            del user_states["other_date"][user_id]
            return
    # После скачивания проверяем, появился ли файл на сервере
    if os.path.isfile(file_name):
        try:
            file_from_pc = FSInputFile(file_name)
            await message.answer_document(file_from_pc, caption=f"Расписание на {text}", reply_markup=main_keyboard)
            await send_as_text2(message, file_name)
        except Exception as e:
            logging.error(f"Ошибка при отправке файла: {e}")
            await message.answer("Произошла ошибка при отправке расписания.", reply_markup=main_keyboard)
    else:
        await message.answer("Расписание не найдено, извините.", reply_markup=main_keyboard)

    del user_states["other_date"][user_id]


# Обработка запросов, не предусмотренных обработчиком бота
@dp.message()
async def any_mess(message: types.Message, **kwargs):
    await message.answer("Пожалуйста, используйте экранные кнопки или команды, которые можно найти с помощью /help", reply_markup=main_keyboard)


scheduler = AsyncIOScheduler()

for days_offset in [0, 1, 2, 3]:
    scheduler.add_job(
        download_schedule,
        'interval',
        minutes=5,
        args=[days_offset],
        misfire_grace_time=30 * (days_offset + 1)
    )

scheduler.add_job(
    morning_schedule_task,
    CronTrigger(hour=7, minute=0),
    misfire_grace_time=300
)

scheduler.add_job(
    evening_schedule_task,
    CronTrigger(hour=20, minute=00),
    misfire_grace_time=300
)


async def start_scheduler():
    scheduler.start()
    logging.info("Планировщик запущен.")
    logging.info("Бот запущен")


async def main():
    asyncio.create_task(start_scheduler())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

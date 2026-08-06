"""
Телеграм-бот планировщик.
Команды:
  /start           - приветствие
  /add <время> <текст>   - добавить задачу (пример: /add 18:00 Купить продукты)
  /list            - список задач на сегодня
  /done <id>       - отметить задачу выполненной
  /delete <id>     - удалить задачу
  /help            - помощь
"""
import asyncio
import logging
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN. Задайте переменную окружения BOT_TOKEN.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Часовой пояс Казахстана (UTC+5) — используем всегда, независимо от того,
# в каком часовом поясе физически работает сервер (Railway обычно UTC).
TZ = ZoneInfo("Asia/Almaty")


def now_local() -> datetime:
    return datetime.now(TZ)


TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    db.init_db()
    await message.answer(
        "Привет! Я твой бот-планировщик.\n\n"
        "Вот что я умею:\n"
        "/add 18:00 Купить продукты — добавить задачу с напоминанием\n"
        "/list — показать задачи на сегодня\n"
        "/done 3 — отметить задачу №3 выполненной\n"
        "/delete 3 — удалить задачу №3\n"
        "/help — эта справка"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await cmd_start(message)


@dp.message(Command("add"))
async def cmd_add(message: Message):
    """
    Формат: /add HH:MM текст задачи
    Пример: /add 18:00 Купить продукты
    """
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "Формат команды: /add ЧЧ:ММ текст задачи\n"
            "Пример: /add 18:00 Купить продукты"
        )
        return

    time_str, task_text = args[1], args[2]
    if not TIME_RE.match(time_str):
        await message.answer("Время указано неверно. Используй формат ЧЧ:ММ, например 09:30")
        return

    task_id = db.add_task(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        text=task_text,
        remind_time=time_str,
    )
    await message.answer(f"Готово! Задача №{task_id} добавлена на {time_str} (повторяется каждый день).")


@dp.message(Command("list"))
async def cmd_list(message: Message):
    today = now_local().strftime("%Y-%m-%d")
    tasks = db.get_tasks_for_today(message.from_user.id, today)

    if not tasks:
        await message.answer("На сегодня задач нет. Добавь через /add ЧЧ:ММ текст")
        return

    lines = ["Задачи на сегодня:\n"]
    for t in tasks:
        lines.append(f"№{t['id']} · {t['remind_time']} · {t['text']}")
    lines.append("\nОтметить выполненной: /done <номер>")
    await message.answer("\n".join(lines))


@dp.message(Command("done"))
async def cmd_done(message: Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Формат: /done <номер задачи>")
        return

    task_id = int(args[1])
    success = db.mark_done(task_id, message.from_user.id)
    if success:
        await message.answer(f"Задача №{task_id} отмечена выполненной ✅")
    else:
        await message.answer("Задача с таким номером не найдена.")


@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Формат: /delete <номер задачи>")
        return

    task_id = int(args[1])
    success = db.delete_task(task_id, message.from_user.id)
    if success:
        await message.answer(f"Задача №{task_id} удалена.")
    else:
        await message.answer("Задача с таким номером не найдена.")


async def check_reminders():
    """Каждую минуту проверяем, есть ли задачи, о которых пора напомнить."""
    now = now_local()
    current_time = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")

    due_tasks = db.get_due_tasks(current_time, today)
    for task in due_tasks:
        try:
            await bot.send_message(task["chat_id"], f"🔔 Напоминание: {task['text']}")
            db.mark_sent(task["id"])
        except Exception as e:
            logger.error(f"Не удалось отправить напоминание {task['id']}: {e}")


async def reset_flags_at_midnight():
    db.reset_daily_sent_flags()


async def main():
    db.init_db()

    scheduler = AsyncIOScheduler(timezone=TZ)
    # Проверяем напоминания каждую минуту
    scheduler.add_job(check_reminders, "interval", minutes=1)
    # В полночь по времени Казахстана сбрасываем флаги отправки для повторяющихся задач
    scheduler.add_job(reset_flags_at_midnight, "cron", hour=0, minute=0)
    scheduler.start()

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

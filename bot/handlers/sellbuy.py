from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
)
import os
import sys

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from client.models import Client
from asgiref.sync import sync_to_async

sellbuy_router = Router()
CHANNEL_ID = -1002615944125
CHANNEL_LINK = "https://t.me/teztezfg"

class SellFSM(StatesGroup):
    status = State()
    name = State()
    desc = State()
    price = State()
    photos = State()
    show_phone = State()
    confirm = State()

def get_status_emoji(status):
    return {
        "Продажа": "💰",
        "Обмен": "🔄",
        "Поиск": "🔎"
    }.get(status, "")

@sync_to_async
def get_client_phone(tg_code):
    try:
        client = Client.objects.get(tg_code=str(tg_code))
        return client.phone or "Не указан"
    except Client.DoesNotExist:
        return "Не указан"

@sellbuy_router.message(Command("sell"))
async def start_sell(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    client = await sync_to_async(Client.objects.filter(tg_code=user_id).first)()
    if not client:
        await message.answer(
            "❗️Вы не зарегистрированы!\n"
            "Пожалуйста, используйте команду \n /start для регистрации.",
            parse_mode="HTML"
        )
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Продать", callback_data="status_sell"),
                InlineKeyboardButton(text="Обмен", callback_data="status_exchange"),
                InlineKeyboardButton(text="Ищу", callback_data="status_search"),
            ]
        ]
    )
    await message.answer(
        "🛒 <b>Создание объявления</b>\n\n"
        "Выберите статус вашего объявления:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.status)

@sellbuy_router.callback_query(SellFSM.status)
async def choose_status(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    status_map = {
        "status_sell": "Продажа",
        "status_exchange": "Обмен",
        "status_search": "Поиск"
    }
    status = status_map.get(callback.data, "Продажа")
    await state.update_data(status=status)
    await callback.message.edit_text(
        f"Статус: <b>{status}</b>\n\n"
        "Введите <b>название</b> товара:",
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.name)

@sellbuy_router.message(SellFSM.name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(
        "📝 Опишите ваш товар как можно подробнее:\n\n"
        "<i>Например: состояние, комплектация, особенности...</i>",
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.desc)

@sellbuy_router.message(SellFSM.desc)
async def get_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer(
        "💵 Укажите цену (только число, например: 1500):",
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.price)

@sellbuy_router.message(SellFSM.price)
async def get_price(message: types.Message, state: FSMContext):
    price_text = message.text.replace(" ", "")
    if not price_text.isdigit():
        await message.answer(
            "❗️Цена должна быть числом. Введите только число, например: 1500",
            parse_mode="HTML"
        )
        return
    await state.update_data(price=price_text)
    await state.update_data(photos=[])
    await message.answer(
        "📸 Пришлите до 10 фотографий товара (по одной).",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.photos)

@sellbuy_router.message(SellFSM.photos)
async def get_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if message.photo:
        if len(photos) >= 10:
            await message.answer(
                "Можно добавить не больше 10 фото.",
                parse_mode="HTML"
            )
            return
        file_id = message.photo[-1].file_id
        photos.append(file_id)
        await state.update_data(photos=photos)
        if len(photos) == 1:
            kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Готово ✅")]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            await message.answer(
                f"Фото {len(photos)}/10 добавлено. Можете добавить ещё или нажмите <b>Готово ✅</b>.",
                reply_markup=kb,
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"Фото {len(photos)}/10 добавлено. Можете добавить ещё или нажмите <b>Готово ✅</b>.",
                parse_mode="HTML"
            )
    elif message.text and "готово" in message.text.lower():
        if not photos:
            await message.answer(
                "Сначала добавьте хотя бы одну фотографию!",
                parse_mode="HTML"
            )
            return
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Показывать номер", callback_data="show_phone_yes"),
                    InlineKeyboardButton(text="Скрыть номер", callback_data="show_phone_no")
                ]
            ]
        )
        await message.answer(
            "📞 Показывать ваш номер телефона в объявлении?",
            reply_markup=kb
        )
        await state.set_state(SellFSM.show_phone)
    else:
        await message.answer(
            "Пришлите фото или нажмите <b>Готово ✅</b>.",
            parse_mode="HTML"
        )

@sellbuy_router.callback_query(SellFSM.show_phone)
async def choose_phone_visibility(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    show_phone = callback.data == "show_phone_yes"
    await state.update_data(show_phone=show_phone)
    await callback.message.edit_text("🔍 Проверьте объявление и подтвердите отправку.")

    data = await state.get_data()
    status = data.get("status")
    name = data.get("name")
    desc = data.get("desc")
    price = data.get("price")
    photos = data.get("photos", [])
    user = callback.from_user

    phone = await get_client_phone(user.id) if show_phone else "Скрыт"
    status_emoji = get_status_emoji(status)
    phone_text = f"📱 <b>Номер:</b> <a>+{phone}</a>" if show_phone else "📱 <b>Номер:</b> <i>Скрыт</i>"
    price_text = f"💵 <b>Цена:</b> {price} ₽"
    contact_link = f"✉️ <a href='tg://user?id={user.id}'>Написать продавцу</a>"

    text = (
        f"{status_emoji} <b>{status}</b>\n"
        f"🏷 <b>{name}</b>\n\n"
        f"{desc}\n\n"
        f"{price_text}\n"
        f"{phone_text}\n"
        f"{contact_link}"
    )

    if photos:
        media = [InputMediaPhoto(media=pid) for pid in photos]
        media[0].caption = text
        media[0].parse_mode = "HTML"
        await callback.message.answer_media_group(media)
    else:
        await callback.message.answer(text, parse_mode="HTML")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Отправить в канал", callback_data="send_to_channel")]
        ]
    )
    await callback.message.answer("Готово к публикации?", reply_markup=kb)
    await state.set_state(SellFSM.confirm)

@sellbuy_router.callback_query(SellFSM.confirm)
async def send_to_channel(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Объявление отправлено!")
    data = await state.get_data()
    status = data.get("status")
    name = data.get("name")
    desc = data.get("desc")
    price = data.get("price")
    photos = data.get("photos", [])
    show_phone = data.get("show_phone")
    user = callback.from_user

    phone = await get_client_phone(user.id) if show_phone else "Скрыт"
    status_emoji = get_status_emoji(status)
    phone_text = f"📱 <b>Номер:</b> <code>+{phone}</code>" if show_phone else "📱 <b>Номер:</b> <i>Скрыт</i>"
    price_text = f"💵 <b>Цена:</b> {price} KGS"
    contact_link = f"✉️ <a href='tg://user?id={user.id}'>Написать продавцу</a>"

    text = (
        f"{status_emoji} <b>{status}</b>\n"
        f"🏷 <b>{name}</b>\n\n"
        f"{desc}\n\n"
        f"{price_text}\n"
        f"{phone_text}\n"
        f"{contact_link}"
    )

    if photos:
        media = [InputMediaPhoto(media=pid) for pid in photos]
        media[0].caption = text
        media[0].parse_mode = "HTML"
        await callback.bot.send_media_group(CHANNEL_ID, media)
    else:
        await callback.bot.send_message(CHANNEL_ID, text, parse_mode="HTML")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁 Посмотреть объявление", url=CHANNEL_LINK)]
        ]
    )
    await callback.message.edit_text(
        "✅ Объявление опубликовано!\n\n"
        "Можете посмотреть его в канале:",
        reply_markup=kb
    )
    await state.clear()
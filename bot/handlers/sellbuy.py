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
from django.utils import timezone
from datetime import timedelta

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from client.models import Client
from asgiref.sync import sync_to_async

sellbuy_router = Router()

CHANNELS = {
    "Веломаркет": {
        "id": -1002615944125,
        "link": "https://t.me/teztezfg",
        "cooldown_field": "next_ability"
    },
    "Бьютимаркет": {
        "id": -1002762051372,
        "link": "https://t.me/tezbueaty/4",
        "cooldown_field": "next_ability_beauty"
    },
    "Техномаркет": {
        "id": -1002897679802,
        "link": "https://t.me/teztechno/2",
        "cooldown_field": "next_ability_techno"
    },
    "Автомотомаркет": {
        "id": -1002549461746,
        "link": "https://t.me/tezautomoto/2",
        "cooldown_field": "next_ability_automoto"
    },
    "Недвижимость": {
        "id": -1002711157981,
        "link": "https://t.me/tezhousing/2",
        "cooldown_field": "next_ability_housing"
    },
    "Работа": {
        "id": -1002788239459,
        "link": "https://t.me/tezzjob/3",
        "cooldown_field": "next_ability_job"
    }
}


class SellFSM(StatesGroup):
    category = State()
    status = State()
    name = State()
    desc = State()
    price = State()
    photos = State()
    show_phone = State()
    confirm = State()

@sync_to_async
def get_client_phone(tg_code):
    try:
        return Client.objects.get(tg_code=str(tg_code)).phone or "Не указан"
    except Client.DoesNotExist:
        return "Не указан"

@sync_to_async
def set_next_ability(client, field_name: str):
    setattr(client, field_name, timezone.now() + timedelta(days=2))
    client.save()

@sellbuy_router.message(Command("sell"))
async def start_sell(message: types.Message, state: FSMContext):
    client = await sync_to_async(Client.objects.filter(tg_code=str(message.from_user.id)).first)()
    if not client:
        await message.answer("❗️ Вы не зарегистрированы! Пожалуйста, используйте /start.")
        return
    if client.is_banned:
        await message.answer("🚫 Вы заблокированы и не можете размещать объявления.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"cat_{name}")]
        for name in CHANNELS.keys()
    ])
    await message.answer(
        "🛒 <b>Создание нового объявления</b>\n\n"
        "📌 Выберите категорию для размещения:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.category)

@sellbuy_router.callback_query(SellFSM.category)
async def choose_category(callback: types.CallbackQuery, state: FSMContext):
    sel = callback.data.removeprefix("cat_")
    client = await sync_to_async(Client.objects.get)(tg_code=str(callback.from_user.id))
    field = CHANNELS[sel]["cooldown_field"]
    now = timezone.now()
    next_allowed = getattr(client, field)
    if next_allowed and next_allowed > now:
        wait = next_allowed - now
        total_minutes = int(wait.total_seconds() // 60)
        days = total_minutes // (24 * 60)
        hours = (total_minutes % (24 * 60)) // 60
        minutes = total_minutes % 60
        parts = []
        if days:
            parts.append(f"{days} дн.")
        if hours:
            parts.append(f"{hours} ч.")
        if minutes:
            parts.append(f"{minutes} мин.")
        if not parts:
            parts.append("менее 1 мин.")
        await callback.message.edit_text(
            f"⏳ Вы уже публиковали в {sel} недавно.\n"
            f"⏱ Следующее размещение будет доступно через: {' '.join(parts)}"
        )
        await state.clear()
        return
    await state.update_data(category=sel)
    
    # Стандартные кнопки для всех категорий
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💰 Продать", callback_data="status_sell"),
        InlineKeyboardButton(text="🔄 Обмен", callback_data="status_exchange"),
        InlineKeyboardButton(text="🔍 Ищу", callback_data="status_search"),
    ]])

    # Специальные кнопки для категорий
    if sel == 'Недвижимость':
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💰 Продать", callback_data="status_sell"),
            InlineKeyboardButton(text="🔑 Сдаю", callback_data="status_hand"),
            InlineKeyboardButton(text="🔍 Ищу", callback_data="status_search"),
        ]])
    elif sel == 'Работа':
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="👨‍💼 Резюме", callback_data="status_resume"),
            InlineKeyboardButton(text="💼 Вакансия", callback_data="status_vacancy"),
        ]])

    await callback.message.edit_text(
        f"🗂 Категория: <b>{sel}</b> \n\n"
        "📌 Выберите тип вашего объявления:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.status)

@sellbuy_router.callback_query(SellFSM.status)
async def choose_status(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    status_map = {
        "status_sell": "💰 Продажа", 
        "status_exchange": "🔄 Обмен", 
        "status_search": "🔍 Поиск", 
        "status_hand": "🔑 Сдаю",
        "status_resume": "👨‍💼 Резюме",
        "status_vacancy": "💼 Вакансия"
    }
    status = status_map.get(callback.data, "💰 Продажа")
    await state.update_data(status=status)
    await callback.message.edit_text(
        f"📝 Теперь введите <b>название товара</b>:",
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.name)

@sellbuy_router.message(SellFSM.name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(
        "📝 <b>Опишите ваш товар подробно:</b>\n\n"
        "<i>• Состояние товара\n"
        "• Комплектация\n"
        "• Особенности\n"
        "• Дополнительная информация</i>",
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.desc)

@sellbuy_router.message(SellFSM.desc)
async def get_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer(
        "💵 <b>Укажите цену в KGS:</b>\n\n"
        "<i>Введите только число, например: 2500</i>",
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.price)

@sellbuy_router.message(SellFSM.price)
async def get_price(message: types.Message, state: FSMContext):
    price_text = message.text.replace(" ", "")
    if not price_text.isdigit():
        await message.answer(
            "❗️ <b>Некорректная цена!</b>\n"
            "Цена должна быть числом. Введите только число, например: 3500",
            parse_mode="HTML"
        )
        return
    await state.update_data(price=price_text, photos=[])
    await message.answer(
        "📸 <b>Добавьте фотографии товара</b>\n\n"
        "• Можно загрузить до 10 фото\n"
        "• Отправляйте по одному фото\n"
        "• Когда закончите, нажмите <b>Готово ✅</b>",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Готово ✅")]],
            resize_keyboard=True,
            one_time_keyboard=True
        ),
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.photos)

@sellbuy_router.message(SellFSM.photos)
async def get_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if message.photo:
        if len(photos) >= 10:
            await message.answer("⚠️ <b>Максимум 10 фото!</b> Нажмите <b>Готово ✅</b>", parse_mode="HTML")
            return
        file_id = message.photo[-1].file_id
        photos.append(file_id)
        await state.update_data(photos=photos)

        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Готово ✅")]],
            resize_keyboard=True
        )
        await message.answer(
            f"✅ Фото {len(photos)}/10 добавлено!\n"
            "Можете добавить ещё или нажать <b>Готово ✅</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )

    elif message.text and message.text.lower() in ["готово", "готово ✅"]:
        if not photos:
            await message.answer("❌ Сначала добавьте хотя бы одну фотографию!", reply_markup=None)
            return

        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Показывать номер", callback_data="show_phone_yes"),
                InlineKeyboardButton(text="❌ Скрыть номер", callback_data="show_phone_no")
            ]]
        )
        await message.answer(
            "📞 <b>Показывать ваш номер телефона в объявлении?</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        await state.set_state(SellFSM.show_phone)
    else:
        await message.answer("📸 Отправьте фото товара или нажмите <b>Готово ✅</b>", parse_mode="HTML")

@sellbuy_router.callback_query(SellFSM.show_phone)
async def choose_phone_visibility(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    show_phone = callback.data == "show_phone_yes"
    await state.update_data(show_phone=show_phone)
    data = await state.get_data()

    # Обновленный словарь эмодзи статусов
    status_emoji = {
        "💰 Продажа": "💰", 
        "🔄 Обмен": "🔄", 
        "🔍 Поиск": "🔍", 
        "🔑 Сдаю": "🔑",
        "👨‍💼 Резюме": "👨‍💼",
        "💼 Вакансия": "💼"
    }
    emoji = status_emoji.get(data["status"], "")
    
    phone_text = f"📱 <b>Телефон:</b> {await get_client_phone(callback.from_user.id)}" if show_phone else "📱 <b>Телефон:</b> <i>Скрыт</i>"

    text = (
        f"<b>{data['status']}</b>\n"
        f"🏷️ <b>{data['name']}</b> \n\n"
        f"{data['desc']}\n\n"
        f"💵 <b>Цена:</b> {data['price']} KGS\n"
        f"{phone_text}\n"
        f"✉️ <a href='tg://user?id={callback.from_user.id}'>Связаться</a>"
    )

    if data['photos']:
        media = [InputMediaPhoto(media=pid) for pid in data['photos']]
        media[0].caption = text
        media[0].parse_mode = "HTML"
        await callback.message.answer_media_group(media)
    else:
        await callback.message.answer(text, parse_mode="HTML")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🚀 Опубликовать", callback_data="confirm_send"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_cancel")
        ]]
    )
    await callback.message.answer(
        "📝 <b>Предпросмотр объявления</b>\n\n"
        "Всё верно? Отправляем в канал?",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(SellFSM.confirm)

@sellbuy_router.callback_query(SellFSM.confirm)
async def send_to_channel(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_cancel":
        await callback.message.edit_text("❌ Публикация отменена")
        await state.clear()
        return

    await callback.answer("⏳ Отправляем объявление...")
    data = await state.get_data()
    chan_info = CHANNELS[data['category']]

    # Обновленный словарь эмодзи статусов
    status_emoji = {
        "💰 Продажа": "💰", 
        "🔄 Обмен": "🔄", 
        "🔍 Поиск": "🔍", 
        "🔑 Сдаю": "🔑",
        "👨‍💼 Резюме": "👨‍💼",
        "💼 Вакансия": "💼"
    }
    emoji = status_emoji.get(data["status"], "")
    
    phone_text = f"📱 <b>Телефон:</b> {await get_client_phone(callback.from_user.id)}" if data.get('show_phone') else "📱 <b>Телефон:</b> <i>Скрыт</i>"

    text = (
        f"<b>{data['status']}</b>\n"
        f"🏷️ <b>{data['name']}</b> \n\n"
        f"{data['desc']}\n\n"
        f"💵 <b>Цена:</b> {data['price']} KGS\n"
        f"{phone_text}\n"
        f"✉️ <a href='tg://user?id={callback.from_user.id}'>Связаться</a>\n"
        f"📢 <a href='https://t.me/tez4917_bot'>Разместить объявление</a>"
    )

    try:
        if data['photos']:
            media = [InputMediaPhoto(media=pid) for pid in data.get('photos', [])]
            media[0].caption = text
            media[0].parse_mode = "HTML"
            await callback.bot.send_media_group(chan_info['id'], media)
        else:
            await callback.bot.send_message(chan_info['id'], text, parse_mode="HTML")

        client = await sync_to_async(Client.objects.get)(tg_code=str(callback.from_user.id))
        await set_next_ability(client, chan_info['cooldown_field'])

        await callback.message.edit_text(
            "✅ <b>Объявление опубликовано!</b>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="👁️ Посмотреть в канале", url=chan_info['link'])]
        ]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка публикации: {str(e)}")

    await state.clear()

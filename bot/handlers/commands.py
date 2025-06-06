from aiogram import types, Router
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
import os
import sys
import importlib
from pathlib import Path

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from client.models import Client
from asgiref.sync import sync_to_async


commands_router = Router()


class RegistrationStates(StatesGroup):
    name = State()
    phone = State()


@sync_to_async
def save_client(name, phone, tg_code):
    client, created = Client.objects.get_or_create(
        tg_code=tg_code,
        defaults={'name': name, 'phone': phone}
    )
    if not created:
        client.name = name
        client.phone = phone
        client.save()
    return client


@commands_router.message(Command('start'))
async def greeting(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="start_registration")]
        ]
    )
    await message.answer_sticker("CAACAgIAAxkBAAEPMn1oKijVIoXpPy2Sc-A80iOFN5HwDgACBQADwDZPE_lqX5qCa011NgQ")
    await message.answer(
        '👋🏻👋🏻Здравствуй, я бот по купле/продаже фг-ништяков и не только!🚴\n'
        'Для начала познакомимся?',
        reply_markup=keyboard
    )


@commands_router.message(Command('help'))
async def help_command(message: types.Message):
    await message.answer(
        '📝Чтобы получить помощь, напиши в поддержку - @isbakks\n'
    )


@commands_router.message(Command('racing'))
async def help_command(message: types.Message):
    await message.answer(
        'В разработке...🤫'
    )


@commands_router.callback_query(lambda c: c.data == "start_registration")
async def start_registration(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Как тебя зовут?")
    await state.set_state(RegistrationStates.name)


@commands_router.message(RegistrationStates.name)
async def ask_phone(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Отправь свой номер телефона кнопкой ниже 👇", reply_markup=kb)
    await state.set_state(RegistrationStates.phone)


@commands_router.message(RegistrationStates.phone)
async def finish_registration(message: types.Message, state: FSMContext):
    data = await state.get_data()
    phone = message.contact.phone_number if message.contact else message.text
    name = data.get('name')
    tg_code = str(message.from_user.id)

    await save_client(name, phone, tg_code)

    await message.answer(
        f"Регистрация завершена!\n"
        f"👇Юзай меню.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.clear()
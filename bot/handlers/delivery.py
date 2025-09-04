from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import ContentType, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from asgiref.sync import sync_to_async
import os, sys, logging
from django.db import transaction
import math
from datetime import datetime
from django.utils import timezone

logger = logging.getLogger(__name__)

# Django setup
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from client.models import CourierOrder, Client, PricingRule, TimeSurcharge
from django.core.exceptions import ObjectDoesNotExist

router = Router()
GROUP_CHAT_ID = '-1002265233281'

ORDER_STATUSES = {
    'new': 'Новый',
    'assigned': 'Назначен',
    'to_a': 'В пути до точки А',
    'to_b': 'В пути до точки Б',
    'arrived': 'Приехал',
    'completed': 'Завершён',
}

# FSM states for delivery
class DeliveryFSM(StatesGroup):
    point_a = State()
    point_b = State()
    comment_order = State()
    confirm_order = State()

# Async helpers to fetch objects
async def aget_object_or_none(model, **kwargs):
    try:
        return await sync_to_async(model.objects.get, thread_sensitive=True)(**kwargs)
    except ObjectDoesNotExist:
        return None

async def aget_object_or_404(model, message: types.Message | types.CallbackQuery, **kwargs):
    obj = await aget_object_or_none(model, **kwargs)
    if not obj:
        msg = '❌ Объект не найден'
        if isinstance(message, types.CallbackQuery):
            await message.answer(msg, show_alert=True)
        else:
            await message.answer(msg)
        return None
    return obj

# Inline keyboard for courier status updates
def get_status_keyboard(order_id, current_status):
    buttons = []
    if current_status == 'assigned':
        buttons.append([
            InlineKeyboardButton(text='🚩 В пути до A', callback_data=f'status_toa_{order_id}')
        ])
    elif current_status == 'to_a':
        buttons.append([
            InlineKeyboardButton(text='🚩 В пути до B', callback_data=f'status_tob_{order_id}')
        ])
    elif current_status == 'to_b':
        buttons.append([
            InlineKeyboardButton(text='✅ Прибыл', callback_data=f'status_arrived_{order_id}')
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Distance and price calculations
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

async def calculate_delivery_price(point_a, point_b):
    lat1, lon1 = point_a
    lat2, lon2 = point_b
    distance = calculate_distance(lat1, lon1, lat2, lon2)
    pricing_rules = await sync_to_async(list, thread_sensitive=True)(PricingRule.objects.all().order_by('min_distance'))
    base_price, per_km_price, multiplier = 0, 0, 1.0
    for rule in pricing_rules:
        max_dist = rule.max_distance if rule.max_distance > 0 else float('inf')
        if rule.min_distance <= distance < max_dist:
            base_price = float(rule.base_price)
            per_km_price = float(rule.per_km_price)
            multiplier = float(rule.multiplier)
            break
    price = (base_price + distance * per_km_price) * multiplier
    time_surcharges = await sync_to_async(list, thread_sensitive=True)(TimeSurcharge.objects.all())
    now = datetime.now().time()
    for surcharge in time_surcharges:
        if surcharge.start_time <= now <= surcharge.end_time:
            price *= float(surcharge.multiplier)
    return round(price, 2), distance

# Sync helper functions for atomic operations
def _create_order_sync(client, data, price, distance):
    with transaction.atomic():
        return CourierOrder.objects.create(
            client=client,
            point_a_lat=data['point_a'][0],
            point_a_lng=data['point_a'][1],
            point_b_lat=data['point_b'][0],
            point_b_lng=data['point_b'][1],
            comment=data.get('comment', ''),
            status='new',
            price=price,
            distance_km=distance,
            created_at=timezone.now()
        )

def _take_order_sync(order_id, courier):
    with transaction.atomic():
        order = (
            CourierOrder.objects
            .select_for_update()
            .select_related('client')
            .get(id=order_id)
        )
        if order.status != 'new':
            raise ValueError("Order already taken")
        order.courier = courier
        order.status = 'assigned'
        order.save()
        return order

# Handlers
@router.message(Command('delivery'))
async def start_delivery(message: types.Message, state: FSMContext):
    client = await aget_object_or_none(Client, tg_code=str(message.from_user.id))
    if not client or getattr(client, 'is_banned', False):
        await message.answer('❗️ Вы не зарегистрированы или заблокированы.')
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='📍 Отправить точку А', request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer('📍 Отправьте точку А (забор):', reply_markup=kb)
    await state.set_state(DeliveryFSM.point_a)

@router.message(DeliveryFSM.point_a, F.content_type == ContentType.LOCATION)
async def get_point_a(message: types.Message, state: FSMContext):
    await state.update_data(point_a=(message.location.latitude, message.location.longitude))
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='📍 Отправить точку Б', request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer('📍 Отправьте точку Б (доставка):', reply_markup=kb)
    await state.set_state(DeliveryFSM.point_b)

@router.message(DeliveryFSM.point_b, F.content_type == ContentType.LOCATION)
async def get_point_b(message: types.Message, state: FSMContext):
    await state.update_data(point_b=(message.location.latitude, message.location.longitude))
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='📝 Пропустить')]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer('📝 Введите комментарий или нажмите «Пропустить»', reply_markup=kb)
    await state.set_state(DeliveryFSM.comment_order)

@router.message(DeliveryFSM.comment_order)
async def get_comment(message: types.Message, state: FSMContext):
    text = message.text if message.content_type == ContentType.TEXT and message.text != '📝 Пропустить' else ''
    await state.update_data(comment=text)
    data = await state.get_data()
    price, distance = await calculate_delivery_price(data['point_a'], data['point_b'])
    preview = (
        f"📌 Предпросмотр заказа:\n"
        f"📍 Точка А: {data['point_a'][0]:.5f}, {data['point_a'][1]:.5f}\n"
        f"📍 Точка Б: {data['point_b'][0]:.5f}, {data['point_b'][1]:.5f}\n"
        f"📏 Расстояние: {distance} км\n"
        f"💰 Стоимость: {price} сом\n"
        f"📝 Комментарий: {text or 'нет'}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Подтвердить', callback_data='delivery_confirm')],
        [InlineKeyboardButton(text='❌ Отменить', callback_data='delivery_cancel')]
    ])
    await message.answer(preview, reply_markup=ReplyKeyboardRemove())
    await message.answer("Подтвердите заказ:", reply_markup=kb)
    await state.set_state(DeliveryFSM.confirm_order)

@router.callback_query(DeliveryFSM.confirm_order)
async def handle_confirmation(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    if cb.data == 'delivery_cancel':
        await cb.message.edit_text('❌ Заказ отменён.')
        await state.clear()
        return

    if cb.data == 'delivery_confirm':
        data = await state.get_data()
        client = await aget_object_or_404(Client, cb.message, tg_code=str(cb.from_user.id))
        if not client:
            await state.clear()
            return
        price, distance = await calculate_delivery_price(data['point_a'], data['point_b'])
        try:
            order = await sync_to_async(_create_order_sync, thread_sensitive=True)(client, data, price, distance)
            text = (
                f"📦 Новый заказ #{order.id}\n"
                f"📍 https://2gis.kg/geo/{order.point_a_lng:.5f},{order.point_a_lat:.5f}\n"
                f"💰 Стоимость: {order.price} сом"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='🚴 Взять заказ', callback_data=f'delivery_take_{order.id}')]
            ])
            await cb.bot.send_message(GROUP_CHAT_ID, text, reply_markup=kb)
            await cb.message.edit_text('✅ Заказ отправлен курьерам.')
        except Exception as e:
            logger.error(f"Order creation error: {e}", exc_info=True)
            await cb.message.answer('❌ Ошибка при создании заказа')
        finally:
            await state.clear()

@router.callback_query(F.data.startswith('delivery_take_'))
async def take_order(cb: types.CallbackQuery):
    print(f"[DEBUG] Callback data: {cb.data}")
    await cb.answer()
    order_id = int(cb.data.split('_')[-1])
    courier = await aget_object_or_404(Client, cb.message, tg_code=str(cb.from_user.id))
    if not courier or getattr(courier, 'is_banned', False):
        return await cb.answer('❗️ Вы не можете брать заказы', show_alert=True)
    try:
        order = await sync_to_async(_take_order_sync, thread_sensitive=True)(order_id, courier)
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.answer('✅ Заказ назначен вам', show_alert=True)
        details = (
            f"🛵 Заказ #{order.id}\n"
            f"👤 Клиент: {order.client.name} - {order.client.phone} | <a href='tg://user?id={order.client.tg_code}'>связаться</a>\n"
            f"📍 A: https://2gis.kg/geo/{order.point_a_lng:.5f},{order.point_a_lat:.5f}\n"
            f"📍 B: https://2gis.kg/geo/{order.point_b_lng:.5f},{order.point_b_lat:.5f}\n"
            f"📏 Расстояние: {order.distance_km} км\n"
            f"💰 Стоимость: {order.price} сом\n"
            f"📝 Комментарий: {order.comment or 'нет'}"
        )
        await cb.bot.send_message(cb.from_user.id, details, parse_mode='HTML')
        status_kb = get_status_keyboard(order.id, 'assigned')
        if status_kb.inline_keyboard:
            await cb.bot.send_message(cb.from_user.id, 'Обновите статус заказа:', reply_markup=status_kb)
    except Exception as e:
        logger.error(f"Order take error: {e}", exc_info=True)
        await cb.answer('❌ Ошибка при взятии заказа', show_alert=True)

@router.callback_query(F.data.regexp(r"^status_(toa|tob|arrived)_[0-9]+$"))
async def update_status(cb: types.CallbackQuery):
    await cb.answer()
    _, action, order_id_str = cb.data.split('_')
    order_id = int(order_id_str)
    status_map = {'toa': 'to_a', 'tob': 'to_b', 'arrived': 'arrived'}
    new_status = status_map.get(action)
    if not new_status:
        return await cb.answer('❌ Неизвестное действие', show_alert=True)

    courier = await aget_object_or_404(Client, cb.message, tg_code=str(cb.from_user.id))
    if not courier:
        return

    # Загружаем заказ вместе с client
    order = await sync_to_async(
        lambda oid: CourierOrder.objects.select_related('client').get(id=oid),
        thread_sensitive=True
    )(order_id)
    if not order:
        return await cb.answer('❌ Заказ не найден', show_alert=True)

    if order.courier_id != courier.id:
        return await cb.answer('❗️ Это не ваш заказ', show_alert=True)

    order.status = new_status
    await sync_to_async(order.save, thread_sensitive=True)()

    await cb.message.edit_text(f"🔄 Статус обновлён: {ORDER_STATUSES[new_status]}")
    # Теперь order.client.tg_code уже в памяти
    await cb.bot.send_message(
        chat_id=int(order.client.tg_code),
        text=f"🔄 Статус заказа #{order.id} обновлён: {ORDER_STATUSES[new_status]}"
    )

    new_kb = get_status_keyboard(order.id, new_status)
    if new_kb.inline_keyboard:
        await cb.bot.send_message(cb.from_user.id, 'Далее:', reply_markup=new_kb)
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ContentType, ReplyKeyboardRemove
from asgiref.sync import sync_to_async
from pathlib import Path
import os, sys
from django.utils import timezone
import logging
from django.db import transaction
from math import sqrt

# Импорты из delivery для расчета цены и GROUP_CHAT_ID
from .delivery import calculate_delivery_price, GROUP_CHAT_ID
from client.models import Category, Shop, Product, Service, Client, Order, OrderItem, CourierOrder

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

shops_router = Router()

class CartFSM(StatesGroup):
    category = State()
    shop = State()
    choosing_type = State()
    choosing_items = State()
    confirm = State()
    delivery_question = State() 
    delivery_point_b = State() 
    delivery_confirm = State()

@sync_to_async
def get_categories():
    return list(Category.objects.all())

@sync_to_async
def get_shops_by_category(cat_id):
    return list(Shop.objects.filter(category_id=cat_id))

@sync_to_async
def get_shop_by_id(shop_id):
    return Shop.objects.select_related('owner').filter(id=shop_id).first()

@sync_to_async
def get_products(shop_id):
    return list(Product.objects.filter(shop_id=shop_id))

@sync_to_async
def get_services(shop_id):
    return list(Service.objects.filter(shop_id=shop_id))

@sync_to_async
def get_client_by_tg(tg_id):
    return Client.objects.filter(tg_code=str(tg_id)).first()

@sync_to_async
def create_order(shop, client, total_price):
    return Order.objects.create(shop=shop, client=client, total_price=total_price)

@sync_to_async
def add_order_items(order, selected_objects, chosen_type):
    for item, qty in selected_objects:
        if chosen_type == 'products':
            OrderItem.objects.create(order=order, product=item, quantity=qty)
        else:
            OrderItem.objects.create(order=order, service=item, quantity=qty)

# Синхронная функция для генерации комментария
def generate_comment_sync(order):
    comment = f"Заказ #{order.id}\nСостав:\n"
    for item in order.items.select_related('product', 'service').all():
        if item.product:
            comment += f"- {item.product.name} x {item.quantity}\n"
        elif item.service:
            comment += f"- {item.service.name} x {item.quantity}\n"
    return comment

ITEMS_PER_PAGE = 5

@shops_router.message(Command("stores"))
async def start_stores(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    if not cats:
        await message.answer("ℹ️ <b>Нет доступных категорий</b>", parse_mode="HTML")
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat.name, callback_data=f"cat_{cat.id}")]
        for cat in cats
    ])
    await message.answer(
        "🛒 <b>Магазины и услуги</b>\n\n"
        "🗂 <b>Выберите категорию:</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(CartFSM.category)

@shops_router.callback_query(lambda c: c.data.startswith("cat_"))
async def choose_category(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    cat_id = int(callback.data.split("_")[1])
    shops = await get_shops_by_category(cat_id)
    if not shops:
        await callback.message.edit_text("ℹ️ <b>Нет магазинов в этой категории</b>", parse_mode="HTML")
        await state.clear()
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=shop.name, callback_data=f"shop_{shop.id}")]
        for shop in shops
    ])
    await callback.message.edit_text(
        "🏪 <b>Выберите магазин:</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(CartFSM.shop)

@shops_router.callback_query(lambda c: c.data.startswith("shop_"))
async def handle_shop_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    shop_id = int(callback.data.split("_")[1])
    shop = await get_shop_by_id(shop_id)
    if not shop:
        await callback.message.edit_text("❌ <b>Магазин не найден</b>", parse_mode="HTML")
        await state.clear()
        return
        
    await state.update_data(shop_id=shop_id)
    products = await get_products(shop_id)
    services = await get_services(shop_id)
    
    text = (
        f"🏪 <b>{shop.name}</b>\n"
        f"👤 <b>Владелец:</b> {shop.owner.name}\n"
        f"📍 <b>Адрес:</b> {shop.address or 'Не указан'}\n"
        f"ℹ️ <b>Описание:</b> {shop.description or 'Без описания'}\n\n"
        "📌 <b>Выберите тип товаров:</b>"
    )
    
    buttons = []
    if products: 
        buttons.append(InlineKeyboardButton(text="🛒 Товары", callback_data="type_products"))
    if services: 
        buttons.append(InlineKeyboardButton(text="🛠 Услуги", callback_data="type_services"))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(CartFSM.choosing_type)

@shops_router.callback_query(lambda c: c.data in ("type_products", "type_services"))
async def handle_type_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    chosen_type = callback.data.split("_")[1]
    
    # Инициализируем корзину, если она еще не создана
    if 'cart_products' not in data:
        data['cart_products'] = {}
    if 'cart_services' not in data:
        data['cart_services'] = {}
    
    await state.update_data(
        chosen_type=chosen_type, 
        current_page=0,
        cart_products=data.get('cart_products', {}),
        cart_services=data.get('cart_services', {})
    )
    await state.set_state(CartFSM.choosing_items)
    await show_items_page(callback, state, 0)

async def show_items_page(callback: CallbackQuery, state: FSMContext, page: int):
    await callback.answer()
    data = await state.get_data()
    shop_id = data["shop_id"]
    chosen = data["chosen_type"]
    all_items = await get_products(shop_id) if chosen == "products" else await get_services(shop_id)
    total = len(all_items)
    start = page * ITEMS_PER_PAGE
    end = min(start + ITEMS_PER_PAGE, total)
    items_slice = all_items[start:end]
    
    text = f"📋 <b>Выберите {chosen}:</b>\n\n"
    for item in items_slice:
        text += f"• {item.name} — <b>{item.price} KGS</b>\n"
    
    keyboard_buttons = []
    for item in items_slice:
        # Проверяем количество в корзине
        cart_key = f"cart_{chosen}"
        cart = data.get(cart_key, {})
        qty = cart.get(item.id, 0)
        btn_text = f"➕ {item.name} ({qty})" if qty > 0 else f"➕ {item.name}"
        keyboard_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"add_{chosen}_{item.id}")])
    
    # Кнопки навигации
    nav = []
    if page > 0: 
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page-1}"))
    if end < total: 
        nav.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page_{page+1}"))
    
    # Основные кнопки
    buttons_row = []
    if data.get('cart_products') or data.get('cart_services'):
        buttons_row.append(InlineKeyboardButton(text="🛒 Корзина", callback_data="items_done"))
    
    buttons_row.append(InlineKeyboardButton(text="↩️ Назад к выбору типа", callback_data="back_to_type"))
    
    if keyboard_buttons:
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons + [nav] + [buttons_row])
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons_row])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(current_page=page)

@shops_router.callback_query(lambda c: c.data.startswith(("add_", "page_", "items_done", "back_to_type")))
async def handle_item_callbacks(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    
    if callback.data == "items_done":
        await confirm_cart(callback, state)
        return
        
    if callback.data == "back_to_type":
        await back_to_type_selection(callback, state)
        return
        
    if callback.data.startswith("page_"):
        page = int(callback.data.split("_")[1])
        await show_items_page(callback, state, page)
        return
        
    parts = callback.data.split("_")
    cart_key = f"cart_{parts[1]}"
    item_id = int(parts[2])
    
    # Обновляем корзину
    cart = data.get(cart_key, {})
    cart[item_id] = cart.get(item_id, 0) + 1
    await state.update_data(**{cart_key: cart})
    
    # Обновляем текущую страницу
    await show_items_page(callback, state, data["current_page"])

async def back_to_type_selection(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    shop_id = data["shop_id"]
    shop = await get_shop_by_id(shop_id)
    products = await get_products(shop_id)
    services = await get_services(shop_id)
    
    text = (
        f"🏪 <b>{shop.name}</b>\n"
        f"👤 <b>Владелец:</b> {shop.owner.name}\n"
        f"📍 <b>Адрес:</b> {shop.address or 'Не указан'}\n"
        f"ℹ️ <b>Описание:</b> {shop.description or 'Без описания'}\n\n"
        "📌 <b>Выберите тип товаров:</b>"
    )
    
    buttons = []
    if products: 
        buttons.append(InlineKeyboardButton(text="🛒 Товары", callback_data="type_products"))
    if services: 
        buttons.append(InlineKeyboardButton(text="🛠 Услуги", callback_data="type_services"))
    
    # Добавляем кнопку корзины, если в ней есть товары
    if data.get('cart_products') or data.get('cart_services'):
        buttons.append(InlineKeyboardButton(text="🛒 Перейти в корзину", callback_data="items_done"))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(CartFSM.choosing_type)

async def confirm_cart(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    shop = await get_shop_by_id(data.get("shop_id"))
    
    # Получаем содержимое корзины
    cart_products = data.get("cart_products", {})
    cart_services = data.get("cart_services", {})
    
    # Получаем полные объекты
    all_products = {p.id: p for p in await get_products(data["shop_id"])}
    all_services = {s.id: s for s in await get_services(data["shop_id"])}
    
    selected_products = []
    selected_services = []
    total_price = 0
    
    # Формируем список товаров
    for pid, qty in cart_products.items():
        if pid in all_products:
            item = all_products[pid]
            selected_products.append((item, qty))
            total_price += item.price * qty
    
    # Формируем список услуг
    for sid, qty in cart_services.items():
        if sid in all_services:
            item = all_services[sid]
            selected_services.append((item, qty))
            total_price += item.price * qty
    
    # Проверяем, что корзина не пуста
    if not selected_products and not selected_services:
        await callback.message.answer("❌ <b>Ваша корзина пуста!</b>", parse_mode="HTML")
        return
    
    # Формируем текст корзины
    text = "🛒 <b>Ваша корзина:</b>\n\n"
    for item, qty in selected_products:
        text += f"• {item.name} — <b>{item.price} KGS</b> x{qty} = <b>{item.price * qty} KGS</b>\n"
    
    for item, qty in selected_services:
        text += f"• {item.name} — <b>{item.price} KGS</b> x{qty} = <b>{item.price * qty} KGS</b>\n"
    
    text += f"\n💰 <b>Итого: {total_price} KGS</b>\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Оформить заказ", callback_data="cart_confirm"),
        InlineKeyboardButton(text="🛒 Продолжить покупки", callback_data="back_to_type"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cart_cancel")
    ]])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(CartFSM.confirm)

@shops_router.callback_query(lambda c: c.data in ("cart_confirm", "cart_cancel", "back_to_type"))
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    
    if callback.data == "cart_cancel":
        await callback.message.edit_text("❌ <b>Заказ отменён</b>", parse_mode="HTML")
        await state.clear()
        return
        
    if callback.data == "back_to_type":
        await back_to_type_selection(callback, state)
        return
        
    client = await get_client_by_tg(callback.from_user.id)
    
    if not client:
        await callback.message.edit_text("❌ <b>Ошибка:</b> Пользователь не найден!", parse_mode="HTML")
        await state.clear()
        return
    
    shop = await get_shop_by_id(data["shop_id"])
    
    # Рассчитываем итоговую сумму
    cart_products = data.get("cart_products", {})
    cart_services = data.get("cart_services", {})
    
    all_products = {p.id: p for p in await get_products(data["shop_id"])}
    all_services = {s.id: s for s in await get_services(data["shop_id"])}
    
    total_price = 0
    selected_products = []
    selected_services = []
    
    for pid, qty in cart_products.items():
        if pid in all_products:
            item = all_products[pid]
            total_price += item.price * qty
            selected_products.append((item, qty))
    
    for sid, qty in cart_services.items():
        if sid in all_services:
            item = all_services[sid]
            total_price += item.price * qty
            selected_services.append((item, qty))
    
    # Создаем заказ
    order = await create_order(shop, client, total_price)
    
    # Добавляем товары и услуги
    if selected_products:
        await add_order_items(order, selected_products, 'products')
    if selected_services:
        await add_order_items(order, selected_services, 'services')
    
    # Формируем сообщение
    text = (
        f"✅ <b>Ваш заказ #{order.id} оформлен!</b>\n\n"
        f"🏪 <b>Магазин:</b> {shop.name}\n"
        f"💰 <b>Сумма:</b> {total_price} KGS\n\n"
        "🚚 Желаете ли вы доставку заказа?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="delivery_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="delivery_no")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await state.update_data(order_id=order.id, shop_id=shop.id)
    await state.set_state(CartFSM.delivery_question)

@shops_router.callback_query(CartFSM.delivery_question, F.data.in_(["delivery_yes", "delivery_no"]))
async def handle_delivery_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    
    if callback.data == "delivery_no":
        try:
            # Получаем данные заказа
            order_id = data['order_id']
            shop_id = data['shop_id']
            
            # Получаем объекты из БД
            order = await sync_to_async(Order.objects.get)(id=order_id)
            shop = await get_shop_by_id(shop_id)
            client = await get_client_by_tg(callback.from_user.id)
            
            # Формируем сообщение для владельца магазина
            owner_message = (
                f"📦 <b>Новый заказ #{order.id}</b>\n"
                f"👤 Клиент: {client.name} ({client.phone})\n"
                f"📅 Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"<b>Состав заказа:</b>\n"
            )
            
            # Получаем элементы заказа
            def get_order_items_sync(order_id):
                order = Order.objects.get(id=order_id)
                return list(order.items.select_related('product', 'service').all())
            
            order_items = await sync_to_async(get_order_items_sync)(order_id)
            
            # Добавляем информацию о товарах/услугах
            for item in order_items:
                if item.product:
                    owner_message += f"  - {item.product.name} × {item.quantity} = {item.product.price * item.quantity} KGS\n"
                elif item.service:
                    owner_message += f"  - {item.service.name} × {item.quantity} = {item.service.price * item.quantity} KGS\n"
            
            owner_message += f"\n💰 <b>Итого: {order.total_price} KGS</b>"
            
            # Отправляем уведомление владельцу магазина
            await callback.bot.send_message(
                chat_id=shop.owner.tg_code,
                text=owner_message,
                parse_mode="HTML"
            )
            
            # Сообщение для покупателя
            await callback.message.edit_text(
                "✅ <b>Заказ завершен! Спасибо за покупку.</b>\n\n"
                "📞 Владелец магазина свяжется с вами для уточнения деталей.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Order notification error: {e}", exc_info=True)
            await callback.message.edit_text(
                "✅ Заказ оформлен! Произошла ошибка при отправке уведомления владельцу.",
                parse_mode="HTML"
            )
        finally:
            await state.clear()
        return
        
    # Если выбрана доставка
    shop = await get_shop_by_id(data['shop_id'])
    
    # Проверяем что в магазине есть координаты
    if not shop.point_a_lat or not shop.point_a_lng:
        await callback.message.answer("❌ В этом магазине не настроена доставка")
        await state.clear()
        return
        
    # Запрашиваем точку Б
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='📍 Отправить точку доставки', request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.answer(
        "📍 Отправьте ваше текущее местоположение (куда нужно привезти заказ):",
        reply_markup=kb
    )
    await state.set_state(CartFSM.delivery_point_b)

@shops_router.message(CartFSM.delivery_point_b, F.content_type == ContentType.LOCATION)
async def get_delivery_point_b(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        shop = await get_shop_by_id(data['shop_id'])
        order_id = data['order_id']
        
        # Используем sync_to_async для работы с ORM
        def get_order_sync(order_id):
            return Order.objects.get(id=order_id)
        
        order = await sync_to_async(get_order_sync)(order_id)
        
        # Генерируем комментарий с использованием синхронной функции
        comment = await sync_to_async(generate_comment_sync)(order)
        
        # Рассчитываем стоимость доставки
        point_a = (shop.point_a_lat, shop.point_a_lng)
        point_b = (message.location.latitude, message.location.longitude)
        price, distance = await calculate_delivery_price(point_a, point_b)
        
        # Сохраняем данные для подтверждения
        await state.update_data(
            point_b=point_b,
            comment=comment,
            price=price,
            distance=distance
        )
        
        # Показываем подтверждение доставки
        preview = (
            f"📦 Доставка заказа #{order.id}\n"
            f"🏪 Магазин: {shop.name}\n"
            f"📍 Откуда: {shop.address or 'магазин'}\n"
            f"📍 Куда: ваше местоположение\n"
            f"📏 Расстояние: {distance:.2f} км\n"
            f"💰 Стоимость доставки: {price:.2f} сом"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='✅ Подтвердить', callback_data='delivery_confirm')],
            [InlineKeyboardButton(text='❌ Отменить', callback_data='delivery_cancel')]
        ])
        
        await message.answer(preview, reply_markup=ReplyKeyboardRemove())
        await message.answer("Подтвердите заказ на доставку:", reply_markup=kb)
        await state.set_state(CartFSM.delivery_confirm)
    except Exception as e:
        logger.error(f"Delivery location error: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обработке местоположения")
        await state.clear()

@shops_router.callback_query(CartFSM.delivery_confirm, F.data.in_(['delivery_confirm', 'delivery_cancel']))
async def handle_delivery_confirmation(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    
    if cb.data == 'delivery_cancel':
        await cb.message.edit_text('❌ Доставка отменена')
        await state.clear()
        return
        
    try:
        data = await state.get_data()
        client = await get_client_by_tg(cb.from_user.id)
        shop = await get_shop_by_id(data['shop_id'])
        point_b = data['point_b']
        
        # Используем sync_to_async для создания заказа
        def create_delivery_order_sync():
            return CourierOrder.objects.create(
                client=client,
                point_a_lat=shop.point_a_lat,
                point_a_lng=shop.point_a_lng,
                point_b_lat=point_b[0],
                point_b_lng=point_b[1],
                comment=data['comment'],
                status='new',
                price=data['price'],
                distance_km=data['distance'],
                created_at=timezone.now()
            )
        
        order = await sync_to_async(create_delivery_order_sync)()
        
        # Отправляем уведомление в группу курьеров
        text = (
            f"📦 Новый заказ доставки #{order.id}\n"
            f"🏪 Из магазина: {shop.name}\n"
            f"📍 Точка А: магазин\n"
            f"📍 Точка Б: клиент\n"
            f"💰 Стоимость: {order.price:.2f} сом\n"
            f"📏 Расстояние: {order.distance_km:.2f} км"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🚴 Взять заказ', callback_data=f'delivery_take_{order.id}')]
        ])
        await cb.bot.send_message(GROUP_CHAT_ID, text, reply_markup=kb)
        
        await cb.message.edit_text('✅ Заказ на доставку отправлен курьерам!')
    except Exception as e:
        logger.error(f"Delivery order error: {e}", exc_info=True)
        await cb.message.answer('❌ Ошибка при оформлении доставки')
    finally:
        await state.clear()

@shops_router.callback_query()
async def catch_all(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
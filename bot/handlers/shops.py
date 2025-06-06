from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from asgiref.sync import sync_to_async
from pathlib import Path
from collections import Counter
import os, sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from client.models import Shop, Product, Service, Client, Order, OrderItem

shops_router = Router()

class CartFSM(StatesGroup):
    shop           = State()
    choosing_type  = State()
    choosing_items = State()
    confirm        = State()

@sync_to_async
def get_all_shops():
    return list(Shop.objects.all())

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
    order = Order.objects.create(
        shop=shop,
        client=client,
        total_price=total_price
    )
    return order

@sync_to_async
def add_order_items(order, selected_objects, chosen_type):
    if chosen_type == "products":
        for item, qty in selected_objects:
            OrderItem.objects.create(order=order, product=item, quantity=qty)
    elif chosen_type == "services":
        for item, qty in selected_objects:
            OrderItem.objects.create(order=order, service=item, quantity=qty)

ITEMS_PER_PAGE = 5

@shops_router.message(Command("repair"))
async def start_repair(message: types.Message, state: FSMContext):
    await state.clear()
    shops = await get_all_shops()
    if not shops:
        await message.answer("ℹ️ В данный момент нет доступных мастерских.")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=shop.name, callback_data=f"shop_{shop.id}")]
            for shop in shops
        ]
    )
    await message.answer("🏪 <b>Выберите мастерскую:</b>", reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(CartFSM.shop)

@shops_router.callback_query(lambda c: c.data.startswith("shop_"))
async def handle_shop_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        shop_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.message.answer("❌ Неверная команда. Повторите /repair.")
        return

    shop = await get_shop_by_id(shop_id)
    if not shop:
        await callback.message.answer("❌ Мастерская не найдена. Повторите /repair.")
        return

    await state.update_data(shop_id=shop_id)
    products = await get_products(shop_id)
    services = await get_services(shop_id)

    text = (
        f"🏪 <b>{shop.name}</b>\n"
        f"👤 Владелец: {shop.owner.name}\n"
        f"📍 Адрес: {shop.address or 'Не указан'}\n"
        f"ℹ️ {shop.description or 'Без описания'}\n\n"
    )

    buttons = []
    if products:
        buttons.append(InlineKeyboardButton(text="🛒 Товары", callback_data="type_products"))
    if services:
        buttons.append(InlineKeyboardButton(text="🛠 Услуги", callback_data="type_services"))

    if not buttons:
        text += "⚠️ В этой мастерской нет ни товаров, ни услуг.\nПопробуйте другую мастерскую: /repair"
        await callback.message.edit_text(text, parse_mode="HTML")
        await state.clear()
        return

    text += "Выберите, что хотите:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(CartFSM.choosing_type)

@shops_router.callback_query(lambda c: c.data in ("type_products", "type_services"))
async def handle_type_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    shop_id = data.get("shop_id")
    if not shop_id:
        await callback.message.answer("❌ Ошибка. Начните с /repair.")
        await state.clear()
        return

    chosen_type = callback.data.split("_")[1]
    cart_products = data.get("cart_products", [])
    cart_services = data.get("cart_services", [])
    await state.update_data(
        chosen_type=chosen_type,
        current_page=0,
        cart_products=cart_products,
        cart_services=cart_services
    )
    await state.set_state(CartFSM.choosing_items)
    await show_items_page(callback, state, page=0)

async def show_items_page(callback: CallbackQuery, state: FSMContext, page: int):
    await callback.answer()
    data = await state.get_data()
    shop_id = data["shop_id"]
    chosen = data["chosen_type"]

    all_items = await get_products(shop_id) if chosen == "products" else await get_services(shop_id)
    total = len(all_items)
    if total == 0:
        await callback.message.edit_text(
            f"⚠️ Нет { 'товаров' if chosen=='products' else 'услуг' } в этой категории.\n"
            "Введите /repair, чтобы начать заново."
        )
        await state.clear()
        return

    start = page * ITEMS_PER_PAGE
    end = min(start + ITEMS_PER_PAGE, total)
    items_slice = all_items[start:end]

    text = f"📋 <b>Выберите {'товары' if chosen=='products' else 'услуги'} (можно несколько):</b>\n"
    for item in items_slice:
        text += f"• {item.name} — {item.price} KGS\n"
    text += "\n"

    keyboard_buttons = []
    for item in items_slice:
        callback_key = f"add_{chosen[:-1]}_{item.id}"
        keyboard_buttons.append([InlineKeyboardButton(text=f"➕ {item.name}", callback_data=callback_key)])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅ Назад", callback_data=f"page_{page-1}"))
    if end < total:
        nav_row.append(InlineKeyboardButton(text="Далее ➡", callback_data=f"page_{page+1}"))
    nav_row.append(InlineKeyboardButton(text="✅ Готово", callback_data="items_done"))

    back_to_type = InlineKeyboardButton(text="🔄 Сменить категорию", callback_data="back_to_type")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=keyboard_buttons + [nav_row] + [[back_to_type]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(current_page=page)

@shops_router.callback_query(lambda c: c.data.startswith(("add_", "page_", "items_done", "back_to_type")))
async def handle_item_callbacks(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    shop_id = data.get("shop_id")
    chosen = data.get("chosen_type")
    current_page = data.get("current_page", 0)

    if not shop_id or not chosen:
        await callback.message.answer("❌ Сессия завершена. Введите /repair для нового заказа.")
        await state.clear()
        return

    if callback.data == "back_to_type":
        shop = await get_shop_by_id(shop_id)
        products = await get_products(shop_id)
        services = await get_services(shop_id)
        text = (
            f"🏪 <b>{shop.name}</b>\n"
            f"👤 Владелец: {shop.owner.name}\n"
            f"📍 Адрес: {shop.address or 'Не указан'}\n"
            f"ℹ️ {shop.description or 'Без описания'}\n\n"
            "Выберите, что хотите:"
        )
        buttons = []
        if products:
            buttons.append(InlineKeyboardButton(text="🛒 Товары", callback_data="type_products"))
        if services:
            buttons.append(InlineKeyboardButton(text="🛠 Услуги", callback_data="type_services"))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CartFSM.choosing_type)
        return

    if callback.data.startswith("page_"):
        try:
            new_page = int(callback.data.split("_")[1])
        except ValueError:
            await callback.message.answer("❌ Некорректная страница.")
            return
        await show_items_page(callback, state, new_page)
        return

    if callback.data == "items_done":
        await confirm_cart(callback, state)
        return

    parts = callback.data.split("_")
    if len(parts) == 3 and parts[0] == "add":
        item_type, item_id_str = parts[1], parts[2]
        try:
            item_id = int(item_id_str)
        except ValueError:
            await callback.message.answer("❌ Неверный ID элемента.")
            return

        if item_type == "product":
            all_items = await get_products(shop_id)
            found = next((i for i in all_items if i.id == item_id), None)
            if not found:
                await callback.message.answer("❌ Этот товар сейчас недоступен.")
                return
            cart_products = data.get("cart_products", [])
            cart_products.append(item_id)
            await state.update_data(cart_products=cart_products)
            count = Counter(cart_products)[item_id]
            await callback.message.answer(f"✔️ «{found.name}» добавлен в корзину (x{count}).")
        elif item_type == "service":
            all_items = await get_services(shop_id)
            found = next((i for i in all_items if i.id == item_id), None)
            if not found:
                await callback.message.answer("❌ Эта услуга сейчас недоступна.")
                return
            cart_services = data.get("cart_services", [])
            cart_services.append(item_id)
            await state.update_data(cart_services=cart_services)
            count = Counter(cart_services)[item_id]
            await callback.message.answer(f"✔️ «{found.name}» добавлена в корзину (x{count}).")
        return

    await callback.message.answer("❌ Некорректная команда. Введите /repair, чтобы начать заново.")

async def confirm_cart(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    shop_id = data.get("shop_id")
    cart_products = data.get("cart_products", [])
    cart_services = data.get("cart_services", [])

    if not cart_products and not cart_services:
        await callback.message.answer("⚠️ Корзина пуста. Добавьте элемент.")
        return

    shop = await get_shop_by_id(shop_id)
    if not shop:
        await callback.message.answer("❌ Ошибка загрузки магазина. Попробуйте /repair.")
        await state.clear()
        return

    all_products = await get_products(shop_id)
    all_services = await get_services(shop_id)

    counter_products = Counter(cart_products)
    counter_services = Counter(cart_services)
    selected_products = []
    selected_services = []
    total_price = 0

    for item in all_products:
        qty = counter_products.get(item.id, 0)
        if qty > 0:
            selected_products.append((item, qty))
            total_price += item.price * qty

    for item in all_services:
        qty = counter_services.get(item.id, 0)
        if qty > 0:
            selected_services.append((item, qty))
            total_price += item.price * qty

    text = "🛒 <b>Ваша корзина:</b>\n\n"
    if selected_products:
        text += "<b>Товары:</b>\n"
        for item, qty in selected_products:
            text += f"• {item.name} — {item.price} KGS x {qty} = {item.price * qty} KGS\n"
    if selected_services:
        text += "<b>Услуги:</b>\n"
        for item, qty in selected_services:
            text += f"• {item.name} — {item.price} KGS x {qty} = {item.price * qty} KGS\n"
    text += f"\n💰 <b>Итого:</b> {total_price} KGS\n\n"
    text += "<i>Если всё верно, нажмите «Оформить заказ».</i>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Оформить заказ", callback_data="cart_confirm"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="cart_cancel")
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(CartFSM.confirm)

@shops_router.callback_query(lambda c: c.data in ("cart_confirm", "cart_cancel"))
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()

    if callback.data == "cart_cancel":
        await callback.message.edit_text("❌ Заказ отменён.")
        await state.clear()
        return

    user = callback.from_user
    client = await get_client_by_tg(user.id)
    if not client:
        await callback.message.answer("❗️ Вы не зарегистрированы! Нажмите /start.")
        await state.clear()
        return

    shop_id = data.get("shop_id")
    cart_products = data.get("cart_products", [])
    cart_services = data.get("cart_services", [])

    shop = await get_shop_by_id(shop_id)
    if not shop:
        await callback.message.answer("❌ Ошибка загрузки магазина. Попробуйте /repair.")
        await state.clear()
        return

    all_products = await get_products(shop_id)
    all_services = await get_services(shop_id)

    counter_products = Counter(cart_products)
    counter_services = Counter(cart_services)
    selected_products = []
    selected_services = []
    total_price = 0

    for item in all_products:
        qty = counter_products.get(item.id, 0)
        if qty > 0:
            selected_products.append((item, qty))
            total_price += item.price * qty

    for item in all_services:
        qty = counter_services.get(item.id, 0)
        if qty > 0:
            selected_services.append((item, qty))
            total_price += item.price * qty

    try:
        order = await create_order(
            shop=shop,
            client=client,
            total_price=total_price
        )
    except Exception as e:
        print("Error creating order:", e)
        await callback.message.edit_text("❌ Не удалось оформить заказ. Попробуйте позже.")
        await state.clear()
        return

    for item, qty in selected_products:
        await add_order_items(order, [(item, qty)], "products")
    for item, qty in selected_services:
        await add_order_items(order, [(item, qty)], "services")

    await callback.message.edit_text(
        f"✅ Ваш заказ #{order.id} оформлен!\n"
        f"Сумма: {total_price} KGS\n"
        "Менеджер свяжется с вами."
    )

    await state.clear()

@shops_router.callback_query()
async def catch_all_callbacks(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    current_state = await state.get_state()
    if current_state:
        await callback.message.answer("❌ Некорректное действие. Введите /repair для нового заказа.")
    else:
        await callback.message.answer("ℹ️ Чтобы сделать заказ, введите /repair.")
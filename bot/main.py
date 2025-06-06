import asyncio
from conf import bot, dp
from handlers.commands import commands_router
from handlers.sellbuy import sellbuy_router
from handlers.shops import shops_router
from aiogram.types import BotCommand


async def set_commands(bot):
    commands = [
        BotCommand(command="start", description="Сменить имя"),
        BotCommand(command="help", description="Поддержка"),
        BotCommand(command="sell", description="Создать объявление"),
        BotCommand(command="repair", description="Запись на ремонт"),
        BotCommand(command="racing", description="Создать гонку"),
    ]
    await bot.set_my_commands(commands)


async def main():
    await set_commands(bot)
    dp.include_router(sellbuy_router)
    dp.include_router(commands_router)
    dp.include_router(shops_router)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
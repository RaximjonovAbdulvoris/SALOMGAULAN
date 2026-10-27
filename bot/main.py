"""SALOM's single-park bot with responsive OCR and operator workflows."""
import logging
import os
from telegram import Update
from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import (Application, ApplicationHandlerStop, CallbackQueryHandler,
    CommandHandler, ConversationHandler, MessageHandler, filters)
from telegram.request import HTTPXRequest
from bot.config import BOT_TOKEN
from bot.premium_emoji import PremiumEmojiBot
from bot.secure_persistence import SecurePersistence
from bot.handlers.driver import build_driver_conversation
from bot.handlers.brand import build_brand_conversation
from bot.handlers.operator import register_operator_handlers, refresh_driver_keyboards
from bot.handlers.start import (MENU_DRIVER, MENU_BRAND, MENU_PAYOUT, start, cancel,
    build_payout_handler)
from bot.warmup import warmup_templates

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def build_application_conversation():
    driver, brand = build_driver_conversation(), build_brand_conversation()
    if set(driver.states) & set(brand.states):
        raise ValueError('Overlapping form states')
    navigation = [CommandHandler('start', start, filters.ChatType.PRIVATE),
                  CommandHandler('cancel', cancel, filters.ChatType.PRIVATE), build_payout_handler()]
    return ConversationHandler(entry_points=navigation + driver.entry_points + brand.entry_points,
        states={**driver.states, **brand.states}, fallbacks=navigation, allow_reentry=True,
        name='application_form', persistent=True)


async def stale_subscription(update, context):
    await update.callback_query.answer('Eski tugma. /start orqali arizani boshlang.', show_alert=True)


async def on_error(update, context):
    error = context.error
    if isinstance(error, Conflict):
        logger.error('Another process is polling this bot token; stop the duplicate instance.')
    elif isinstance(error, (NetworkError, TimedOut)):
        logger.warning('Telegram connection interrupted (%s)', type(error).__name__)
    else:
        logger.error('Unhandled bot error (%s)', type(error).__name__)
        if isinstance(update, Update) and update.effective_chat:
            try:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                    text='Texnik xatolik yuz berdi. /start orqali qayta urinib ko‘ring.')
            except Exception:
                pass


async def refresh_controls(context):
    await refresh_driver_keyboards(context.application)


async def post_init(application):
    from bot.legacy_migration import migrate_records
    migrate_records(application.bot_data)
    from bot.presentation import load_emoji_packs
    try:
        await load_emoji_packs(application)
    except Exception as error:
        logger.warning("Premium assets unavailable (%s); continuing with standard icons.", type(error).__name__)
    await warmup_templates(application)
    application.job_queue.run_once(refresh_controls, when=2)
    from bot.background_ocr import resume_pending
    application.job_queue.run_repeating(resume_pending, interval=15, first=0)


def register_handlers(app):
    app.add_handler(build_application_conversation())
    from bot.asset_ids import asset_id
    app.add_handler(CommandHandler('asset_id', asset_id))
    app.add_handler(CallbackQueryHandler(stale_subscription, pattern=r'^(?:driver|brand):check_membership$'))
    register_operator_handlers(app)
    app.add_error_handler(on_error)


def main():
    request = HTTPXRequest(connection_pool_size=20, connect_timeout=30, read_timeout=60,
                           write_timeout=60, pool_timeout=10)
    polling = HTTPXRequest(connection_pool_size=8, connect_timeout=30, read_timeout=40,
                           write_timeout=40)
    persistence = SecurePersistence(filepath=os.path.join(os.environ.get('PERSIST_DIR', '.'), 'bot_persistence.pkl'))
    app = (Application.builder().bot(PremiumEmojiBot(BOT_TOKEN, request=request, get_updates_request=polling))
           .persistence(persistence).post_init(post_init).build())
    register_handlers(app)
    logger.info('WB SALOM bot ishga tushdi.')
    app.run_polling(allowed_updates=['message', 'callback_query'])


if __name__ == '__main__':
    main()

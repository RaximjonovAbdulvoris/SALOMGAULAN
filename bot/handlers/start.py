from telegram import ReplyKeyboardMarkup, Update
from bot.presentation import menu_button
from bot.contact_info import PHONE_DISPLAY, SUPPORT_HANDLE, PAYOUT_HANDLE
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

MENU_DRIVER = "📝 Ulanish uchun Ariza"
MENU_SPECTRE = "⚡ Spectre Energyga ariza"
MENU_BRAND = "🎨 Brend Ariza"
MENU_PAYOUT = "💰 PUL YECHISH BOTI"

def main_keyboard(region=None):
    # Build after premium assets load; cached import-time icons can be stale.
    return ReplyKeyboardMarkup(
        [[menu_button(MENU_DRIVER, icon='DRIVER')],
         [menu_button(MENU_BRAND, icon='BRAND')],
         [menu_button(MENU_SPECTRE, icon='SPECTRE')],
         [menu_button(MENU_PAYOUT, icon='PAYOUT')]], resize_keyboard=True)


MAIN_KEYBOARD = main_keyboard()

WELCOME_TEXT = (
    "🚖 *WB SALOM TAXI* botiga xush kelibsiz!\n\n"
    "Quyidagi menyulardan birini tanlang:\n\n"
    "📝 *Ulanish uchun Ariza* — Haydovchilik uchun ariza\n"
    "🎨 *Brend Ariza* — Mashinangizni brendlash uchun ariza\n"
    "⚡ *Spectre Energyga ariza* — Spectre uchun ariza\n"
    "💰 *PUL YECHISH BOTI* — Pul yechish va aloqa ma'lumotlari"
)

PAYOUT_TEXT = (
    f"💰 *Pul yechish boti:* {PAYOUT_HANDLE}\n\n"
    f"📞 *Telefon:* {PHONE_DISPLAY}\n"
    f"✉️ *Telegram aloqa:* {SUPPORT_HANDLE}"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat.type != "private":
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def show_payout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        PAYOUT_TEXT,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


def build_payout_handler() -> MessageHandler:
    return MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^(?:💰 )?PUL YECHISH BOTI$"), show_payout)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Bekor qilindi. Qaytadan boshlash uchun /start bosing.",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def require_region(update, context, allowed_regions=None):
    return update.effective_chat.type == 'private'

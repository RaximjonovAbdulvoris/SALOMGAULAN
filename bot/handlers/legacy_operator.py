"""Move complete applications between operator queues and the archive."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.config import ARCHIVE_GROUP, CHALA_RASM_GROUP, OTHER_PARK_GROUP

logger = logging.getLogger(__name__)
READY_TEXT = (
    "✅ SALOM TAXiga arizangiz muvaffaqiyatli qabul qilindi!\n\n"
    "📞 Tez orada operatorlarimiz siz bilan bog'lanishadi.\n\n"
    "💬 Savollar uchun park operatoriga murojaat qiling."
)


def build_operator_keyboard(application_id, in_progress=False, stage="main"):
    def button(text, action):
        return InlineKeyboardButton(text, callback_data=f"op:{action}:{application_id}")

    if stage == "main":
        rows = [[button("✅ Tayyor", "ready")],
                [button("📷 Chala rasm", "incomplete"), button("🚕 Boshqa park", "other")]]
    else:
        rows = [[button("✅ Tayyor", "ready"), button("🗑 O'chirish", "delete")]]
    rows.append([button("🟡 Jarayonda" if in_progress else "🔴 Jarayonda", "progress")])
    return InlineKeyboardMarkup(rows)


async def _save(context):
    # Store transfer progress before deleting originals, including across restarts.
    await context.application.update_persistence()
    if context.application.persistence:
        await context.application.persistence.flush()


async def _delete_messages(bot, chat_id, message_ids):
    remaining = []
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except BadRequest as exc:
            if "message to delete not found" not in str(exc).lower():
                remaining.append(message_id)
                logger.warning("Could not delete %s/%s: %s", chat_id, message_id, exc)
        except Exception as exc:
            remaining.append(message_id)
            logger.warning("Could not delete %s/%s: %s", chat_id, message_id, exc)
    return remaining


async def _finish_transfer(context, records, key, record):
    pending = record["pending_cleanup"]
    # Keep the control message until every photo has been removed, so retry works.
    pending["photo_msg_ids"] = await _delete_messages(
        context.bot, pending["group_chat_id"], pending["photo_msg_ids"]
    )
    if not pending["photo_msg_ids"]:
        left = await _delete_messages(context.bot, pending["group_chat_id"], [pending["kb_msg_id"]])
        if not left:
            record.pop("pending_cleanup")
            if record["stage"] in ("archive", "deleted"):
                records.pop(key, None)
    await _save(context)
    return "pending_cleanup" not in record


async def on_operator_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data or not query.message:
        return
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, action, key = parts
    records = context.bot_data.setdefault("app_messages", {})
    # Existing buttons used numeric user IDs; preserve them where records exist.
    if key not in records and key.isdigit() and int(key) in records:
        key = int(key)
    record = records.get(key)
    if not record:
        await query.answer("Bu ariza allaqachon ko'chirilgan yoki o'chirilgan.", show_alert=True)
        return
    pending = record.get("pending_cleanup")
    locations = [record] + ([pending] if pending else [])
    chat_id = query.message.chat_id
    if not any(str(r["group_chat_id"]) == str(chat_id)
               and r["kb_msg_id"] == query.message.message_id for r in locations):
        await query.answer("Bu eski yoki boshqa arizaning tugmasi.", show_alert=True)
        return
    await query.answer()

    async def notice(text):
        await context.bot.send_message(chat_id=chat_id, text=text)

    if pending:
        done = await _finish_transfer(context, records, key, record)
        await notice("✅ Oldingi guruhdagi ariza tozalandi." if done else
                     "⚠️ Ayrim xabarlar o'chmadi. Botning o'chirish huquqini tekshirib, tugmani qayta bosing.")
        return

    stage = record.get("stage", "main")
    if action == "progress":
        if not record.get("in_progress"):
            await query.edit_message_reply_markup(
                reply_markup=build_operator_keyboard(key, True, stage))
            record["in_progress"] = True
            await _save(context)
        return
    allowed = {"ready", "incomplete", "other"} if stage == "main" else {"ready", "delete"}
    if action not in allowed:
        await notice("Bu tugma endi ishlatilmaydi. Arizaning yangi tugmalaridan foydalaning.")
        return

    source = {"group_chat_id": record["group_chat_id"],
              "photo_msg_ids": list(record["photo_msg_ids"]), "kb_msg_id": record["kb_msg_id"]}
    if action == "delete":
        record.update(stage="deleted", pending_cleanup=source)
        await _save(context)
    else:
        destination, new_stage = {
            "ready": (ARCHIVE_GROUP, "archive"),
            "incomplete": (CHALA_RASM_GROUP, "incomplete"),
            "other": (OTHER_PARK_GROUP, "other"),
        }[action]
        if not destination or str(destination) == str(source["group_chat_id"]):
            await notice("⚠️ Manzil guruhi sozlanmagan yoki joriy guruh bilan bir xil. Ariza o'chirilmadi.")
            return
        # Remove any known partial copy before attempting the transfer again.
        rollback = record.get("rollback")
        if rollback:
            rollback["ids"] = await _delete_messages(context.bot, rollback["chat_id"], rollback["ids"])
            await _save(context)
            if rollback["ids"]:
                await notice("⚠️ Oldingi qisman nusxa tozalanmadi. Manzil guruhida botga o'chirish huquqini bering.")
                return
            record.pop("rollback")
        copied = []
        try:
            photos = sorted(source["photo_msg_ids"])
            if not photos:
                raise ValueError("Ariza rasmlari topilmadi")
            result = await context.bot.copy_messages(
                chat_id=destination, from_chat_id=source["group_chat_id"], message_ids=photos)
            copied.extend(item.message_id for item in result)
            # Telegram can silently skip missing messages: never delete originals then.
            if len(copied) != len(photos):
                raise ValueError("Barcha rasmlar ko'chirilmadi")
            photo_ids = list(copied)
            info = await context.bot.copy_message(
                chat_id=destination, from_chat_id=source["group_chat_id"],
                message_id=source["kb_msg_id"],
                reply_markup=(InlineKeyboardMarkup([]) if new_stage == "archive" else
                              build_operator_keyboard(key, stage=new_stage)))
            copied.append(info.message_id)
        except Exception:
            logger.exception("Application transfer failed; originals retained")
            remaining = await _delete_messages(context.bot, destination, copied)
            if remaining:
                record["rollback"] = {"chat_id": destination, "ids": remaining}
            await _save(context)
            await notice("⚠️ Ariza to'liq ko'chmadi. Asl ariza saqlandi. Guruh sozlamalari va bot huquqlarini tekshirib, qayta bosing.")
            return
        record.update(group_chat_id=destination, photo_msg_ids=photo_ids,
                      kb_msg_id=info.message_id, stage=new_stage,
                      in_progress=False, pending_cleanup=source)
        await _save(context)
        if action == "ready":
            try:
                await context.bot.send_message(chat_id=record.get("user_id", key), text=READY_TEXT)
            except Exception:
                logger.warning("Could not notify applicant for %s", key, exc_info=True)

    if not await _finish_transfer(context, records, key, record):
        await notice("⚠️ Ayrim eski xabarlar o'chmadi. Botning o'chirish huquqini tekshirib, tugmani qayta bosing. Qayta nusxa yuborilmaydi.")


async def obsolete_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Izoh orqali yozishish o'chirilgan.", show_alert=True)


def register_operator_handlers(app):
    app.add_handler(CallbackQueryHandler(on_operator_button, pattern=r"^op:"))
    app.add_handler(CallbackQueryHandler(obsolete_reply, pattern=r"^user:reply:"))

"""Upgrade SALOM's UUID records without touching an interrupted old transfer."""
import logging

logger = logging.getLogger(__name__)


def migrate_records(bot_data):
    applications = bot_data.setdefault('applications', {})
    for legacy_id, record in list(bot_data.get('app_messages', {}).items()):
        if not isinstance(record, dict) or 'user_id' not in record:
            continue
        if record.get('pending_cleanup') or record.get('rollback'):
            continue  # The old transfer handler must finish its own checkpoint.
        if record.get('stage', 'main') in ('archive', 'deleted'):
            continue
        try:
            key = int(record['group_chat_id']), int(record['kb_msg_id'])
            applicant = int(record['user_id'])
        except (KeyError, TypeError, ValueError):
            logger.warning('Legacy application has invalid metadata; left unchanged.')
            continue
        if key in applications and applications[key] is not record:
            continue
        record.setdefault('application_key', key)
        record.setdefault('applicant_id', applicant)
        record.setdefault('kind', 'driver')
        record.setdefault('region', 'salom')
        record.setdefault('applicant_name', '')
        record.setdefault('username', '')
        record.setdefault('archive_state', {'photos': {}, 'kb': False})
        if record.get('stage') in ('incomplete', 'other'):
            record.setdefault('queue_kind', 'incomplete' if record['stage'] == 'incomplete' else 'otherpark')
        applications[key] = record
        if record.get('in_progress'):
            bot_data.setdefault('progress_state', {}).setdefault(key, True)


async def handle_pending(update, context):
    """Resume only exact old source/destination callbacks, after admin verification."""
    query = update.callback_query
    parts = (query.data or '').split(':', 2) if query else []
    if len(parts) != 3:
        return False
    records = context.bot_data.get('app_messages', {})
    record = records.get(parts[2])
    if record is None and parts[2].isdigit():
        record = records.get(int(parts[2]))
    if not isinstance(record, dict) or not (record.get('pending_cleanup') or record.get('rollback')):
        return False
    chat, user = update.effective_chat, update.effective_user
    if not query.message or not chat or not user or getattr(query.message, 'sender_chat', None):
        await query.answer('Administrator profilingizdan foydalaning.', show_alert=True)
        return True
    locations = [record, record.get('pending_cleanup') or {}]
    if not any(str(r.get('group_chat_id')) == str(chat.id) and r.get('kb_msg_id') == query.message.message_id for r in locations):
        await query.answer('Bu boshqa arizaning tugmasi.', show_alert=True)
        return True
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
    except Exception:
        await query.answer('Operator huquqini tekshirib bo‘lmadi.', show_alert=True)
        return True
    if member.status not in ('administrator', 'creator'):
        await query.answer('Bu amal faqat administratorlar uchun.', show_alert=True)
        return True
    from bot.handlers.legacy_operator import on_operator_button
    await on_operator_button(update, context)
    migrate_records(context.bot_data)
    return True

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

for name in ('TELEGRAM_BOT_TOKEN', 'DRIVER_GROUP_1', 'DRIVER_GROUP_2', 'BRAND_GROUP'):
    os.environ.setdefault(name, '123:test' if name == 'TELEGRAM_BOT_TOKEN' else '-1001')

from bot.handlers import legacy_operator as op
from bot.handlers.driver import _send_to_driver_group
from bot.counter import _counters
from telegram.error import Forbidden


class OperatorTests(unittest.IsolatedAsyncioTestCase):
    def setup_case(self, stage='main', action='incomplete'):
        record = dict(user_id=42, group_chat_id=-1001, photo_msg_ids=[10, 11],
                      kb_msg_id=12, stage=stage, in_progress=False)
        bot = SimpleNamespace(copy_messages=AsyncMock(return_value=[SimpleNamespace(message_id=20), SimpleNamespace(message_id=21)]),
                              copy_message=AsyncMock(return_value=SimpleNamespace(message_id=22)),
                              delete_message=AsyncMock(), send_message=AsyncMock())
        application = SimpleNamespace(update_persistence=AsyncMock(), persistence=SimpleNamespace(flush=AsyncMock()))
        context = SimpleNamespace(bot=bot, bot_data={'app_messages': {'abc': record}}, application=application)
        query = SimpleNamespace(data=f'op:{action}:abc', message=SimpleNamespace(chat_id=-1001, message_id=12),
                                answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
        return record, context, SimpleNamespace(callback_query=query)

    def test_keyboards(self):
        for stage in ('main', 'incomplete', 'other'):
            for progress in (False, True):
                rows = op.build_operator_keyboard('abc', progress, stage).inline_keyboard
                actions = {b.callback_data.split(':')[1] for row in rows for b in row}
                self.assertEqual(actions, {'ready', 'incomplete', 'other', 'progress'} if stage == 'main' else {'ready', 'delete', 'progress'})
                self.assertIn('🟡' if progress else '🔴', rows[-1][0].text)

    async def test_move_both_queues_resets_progress(self):
        for action, setting, stage in [('incomplete', 'CHALA_RASM_GROUP', 'incomplete'), ('other', 'OTHER_PARK_GROUP', 'other')]:
            record, ctx, update = self.setup_case(action=action)
            record['in_progress'] = True
            with patch.object(op, setting, '-1002'):
                await op.on_operator_button(update, ctx)
            self.assertEqual(record['stage'], stage)
            self.assertFalse(record['in_progress'])
            self.assertEqual(record['photo_msg_ids'], [20, 21])
            self.assertEqual(ctx.bot.delete_message.await_count, 3)
            self.assertNotIn('pending_cleanup', record)

    async def test_partial_copy_keeps_originals(self):
        record, ctx, update = self.setup_case()
        ctx.bot.copy_messages.return_value = [SimpleNamespace(message_id=20)]
        with patch.object(op, 'CHALA_RASM_GROUP', '-1002'):
            await op.on_operator_button(update, ctx)
        self.assertEqual(record['group_chat_id'], -1001)
        ctx.bot.delete_message.assert_awaited_once_with(chat_id='-1002', message_id=20)

    async def test_info_failure_keeps_originals(self):
        record, ctx, update = self.setup_case()
        ctx.bot.copy_message.side_effect = RuntimeError('unavailable')
        with patch.object(op, 'CHALA_RASM_GROUP', '-1002'):
            await op.on_operator_button(update, ctx)
        self.assertEqual(record['group_chat_id'], -1001)
        self.assertTrue(all(c.kwargs['chat_id'] == '-1002' for c in ctx.bot.delete_message.await_args_list))

    async def test_missing_destination_does_not_delete(self):
        record, ctx, update = self.setup_case(action='ready')
        with patch.object(op, 'ARCHIVE_GROUP', ''):
            await op.on_operator_button(update, ctx)
        ctx.bot.delete_message.assert_not_awaited()
        ctx.bot.copy_messages.assert_not_awaited()

    async def test_archive_from_every_stage_has_no_buttons(self):
        for stage in ('main', 'incomplete', 'other'):
            record, ctx, update = self.setup_case(stage=stage, action='ready')
            with patch.object(op, 'ARCHIVE_GROUP', '-1009'):
                await op.on_operator_button(update, ctx)
            self.assertEqual(ctx.bot.copy_message.call_args.kwargs['reply_markup'].inline_keyboard, ())
            self.assertNotIn('abc', ctx.bot_data['app_messages'])

    async def test_delete_secondary_only(self):
        for stage in ('main', 'incomplete', 'other'):
            record, ctx, update = self.setup_case(stage=stage, action='delete')
            await op.on_operator_button(update, ctx)
            self.assertEqual(ctx.bot.delete_message.await_count, 0 if stage == 'main' else 3)
            ctx.bot.copy_messages.assert_not_awaited()

    async def test_progress_every_stage(self):
        for stage in ('main', 'incomplete', 'other'):
            record, ctx, update = self.setup_case(stage=stage, action='progress')
            await op.on_operator_button(update, ctx)
            self.assertTrue(record['in_progress'])
            await op.on_operator_button(update, ctx)
            update.callback_query.edit_message_reply_markup.assert_awaited_once()

    async def test_cleanup_retry_does_not_copy_again(self):
        record, ctx, update = self.setup_case()
        ctx.bot.delete_message.side_effect = Forbidden('no delete permission')
        with patch.object(op, 'CHALA_RASM_GROUP', '-1002'):
            await op.on_operator_button(update, ctx)
            self.assertIn('pending_cleanup', record)
            ctx.bot.delete_message.side_effect = None
            await op.on_operator_button(update, ctx)
        ctx.bot.copy_messages.assert_awaited_once()
        self.assertNotIn('pending_cleanup', record)

    async def test_stale_button_cannot_affect_new_location(self):
        record, ctx, update = self.setup_case()
        update.callback_query.message.message_id = 999
        await op.on_operator_button(update, ctx)
        ctx.bot.copy_messages.assert_not_awaited()
        ctx.bot.delete_message.assert_not_awaited()

    async def test_legacy_record(self):
        record, ctx, update = self.setup_case(action='progress')
        ctx.bot_data['app_messages'] = {42: record}
        update.callback_query.data = 'op:progress:42'
        await op.on_operator_button(update, ctx)
        self.assertTrue(record['in_progress'])



if __name__ == '__main__':
    unittest.main()

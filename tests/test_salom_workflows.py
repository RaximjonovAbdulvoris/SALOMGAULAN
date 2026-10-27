import asyncio
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import AsyncMock, patch
from telegram.ext import ConversationHandler
from telegram.error import BadRequest
from bot.handlers import brand, driver, operator, start
from bot.legacy_migration import migrate_records
from bot.main import build_application_conversation
from bot.application_ids import application_code
from bot.route_settings import save_settings, read_settings
from bot.configure import problems
from test_regions import context, update
from test_operator_safety import _update, FakeBot, FakeMessage


class SalomWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_menu_has_four_actions_and_one_form_machine(self):
        texts = [b.text for row in start.MAIN_KEYBOARD.keyboard for b in row]
        self.assertEqual(texts, [start.MENU_DRIVER, start.MENU_BRAND, start.MENU_SPECTRE, start.MENU_PAYOUT])
        self.assertTrue(hasattr(brand, 'start_spectre'))
        self.assertIn('Spectre', start.WELCOME_TEXT)
        self.assertNotIn('Hudud', start.WELCOME_TEXT)
        conv = build_application_conversation()
        self.assertTrue(conv.persistent)
        self.assertEqual(len(conv.states), len(driver.build_driver_conversation().states) + len(brand.build_brand_conversation().states))
        self.assertTrue(set(driver.build_driver_conversation().states).isdisjoint(brand.build_brand_conversation().states))

    async def test_name_then_no_passport_back_prompt(self):
        ctx = context()
        with patch('bot.handlers.driver.driver_groups', return_value=['-1001', '-1002']):
            self.assertEqual(await driver.start_driver(update(), ctx), driver.NAME)
        self.assertEqual(ctx.user_data['_application_region'], 'salom')
        self.assertEqual(await driver.get_name(update('Test Person'), ctx), driver.PHONE)
        msg = update('+998 90 123 45 67')
        self.assertEqual(await driver.get_phone(msg, ctx), driver.WARN_DOCS)
        self.assertEqual(ctx.user_data['phone'], '998901234567')
        photo = update()
        photo.message.photo = [N(file_id='passport')]
        with patch('bot.handlers.driver._send_prompt', new_callable=AsyncMock) as prompt:
            self.assertEqual(await driver.get_passport_front(photo, ctx), driver.LICENSE_FRONT)
            self.assertEqual(prompt.await_args.args[3], 'license_front')
        self.assertNotIn('passport_back', ctx.user_data)

    async def test_dispatch_rotates_two_groups_and_preserves_repeated_applications(self):
        from bot.counter import _counters
        _counters.clear()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PERSIST_DIR': tmp, 'DOCUMENT_AI_ENABLED': '0'}), \
             patch('bot.handlers.driver.driver_groups', return_value=['-1001', '-1002']):
            ctx = context()
            ids = iter(range(100, 200))
            async def album(**kwargs):
                return [N(message_id=next(ids)) for _ in kwargs['media']]
            async def message(**kwargs):
                return N(message_id=next(ids))
            ctx.bot.send_media_group = AsyncMock(side_effect=album)
            ctx.bot.send_message = AsyncMock(side_effect=message)
            for _ in range(3):
                ctx.user_data = dict(user_id=42, user_username='test', _application_region='salom',
                    phone='998901234567', car_plate='01A123BC', passport_front='p', license_front='l',
                    tech_front='tf', tech_back='tb', selfie='s', litsenziya='lic', car_photos=['c1', 'c2', 'c3', 'c4'])
                await driver._send_to_driver_group(ctx)
            records = list(ctx.bot_data['applications'].values())
            self.assertEqual([r['group_chat_id'] for r in records], [-1001, -1002, -1001])
            self.assertEqual([r['code'] for r in records], ['1', '2', '3'])
            self.assertEqual(len(ctx.bot_data['applications']), 3)
            self.assertTrue(all(r['media_albums'] for r in records))
            self.assertNotIn('Hudud:', ctx.bot.send_message.await_args.kwargs['text'])

    async def test_brand_stays_plain_without_counter_or_approval(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PERSIST_DIR': tmp, 'BRAND_GROUP': '-1003'}):
            ctx = context()
            ctx.user_data.update(_application_region='salom', b_name='Test Person', b_phone='998901234567',
                b_model='Cobalt', b_year='2024', b_color='Oq')
            self.assertEqual(await brand.brand_get_plate(update('01A123BC'), ctx), ConversationHandler.END)
            text = ctx.bot.send_message.await_args.kwargs['text']
            self.assertIn('BREND', text)
            self.assertNotIn('LD-', text)
            self.assertIsNone(ctx.bot.send_message.await_args.kwargs['reply_markup'])
            self.assertFalse(Path(tmp, 'application_numbers.sqlite3').exists())
            self.assertFalse(ctx.bot_data.get('applications'))

    async def test_known_brand_failure_keeps_fields_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PERSIST_DIR': tmp, 'BRAND_GROUP': '-1003'}):
            ctx = context()
            ctx.user_data.update(_application_region='salom', b_name='Test Person', b_phone='998901234567',
                b_model='Cobalt', b_year='2024', b_color='Oq')
            ctx.bot.send_message.side_effect = BadRequest('failure')
            self.assertEqual(await brand.brand_get_plate(update('01A123BC'), ctx), brand.BRAND_PLATE)
            self.assertEqual(ctx.user_data['b_name'], 'Test Person')

    def test_counter_never_allocates_for_started_or_cancelled_form(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PERSIST_DIR': tmp}):
            self.assertEqual(application_code({}), '1')
            data = {}
            self.assertEqual(application_code(data), '2')
            self.assertEqual(application_code(data), '2')

    def test_route_settings_do_not_copy_another_bot_or_accept_duplicate_groups(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'PERSIST_DIR': tmp}):
            settings = dict(DRIVER_GROUP_1='-101', DRIVER_GROUP_2='-102', BRAND_GROUP='-103',
                CHALA_RASM_GROUP='-104', OTHER_PARK_GROUP='-105', ARCHIVE_GROUP='-106',
                SPECTRE_GROUP='-107')
            save_settings(settings)
            self.assertEqual(read_settings(), settings)
            self.assertEqual(problems(), [])
            save_settings({'OTHER_PARK_GROUP': '-104'})
            self.assertTrue(problems())


class LegacyMigrationTests(unittest.IsolatedAsyncioTestCase):
    def setup_record(self, stage='main', admin=True):
        bot = FakeBot()
        bot.get_chat_member = AsyncMock(return_value=N(status='administrator' if admin else 'member'))
        record = dict(user_id=9, stage=stage, in_progress=False, group_chat_id=-1001,
                      kb_msg_id=20, photo_msg_ids=[21, 22])
        ctx = N(bot=bot, bot_data={'app_messages': {'old-uuid': record}})
        event = _update('op:progress:old-uuid', FakeMessage(chat_id=-1001, message_id=20))
        return ctx, record, event

    async def test_old_uuid_buttons_toggle_and_preserve_message_identity(self):
        ctx, record, event = self.setup_record()
        await operator.on_operator_button(event, ctx)
        self.assertTrue(ctx.bot_data['progress_state'][(-1001, 20)])
        await operator.on_operator_button(event, ctx)
        self.assertFalse(ctx.bot_data['progress_state'][(-1001, 20)])
        self.assertIs(ctx.bot_data['applications'][(-1001, 20)], record)
        self.assertEqual(record['photo_msg_ids'], [21, 22])
        self.assertNotIn('code', record)

    async def test_non_admin_and_stale_uuid_cannot_act(self):
        ctx, record, event = self.setup_record(admin=False)
        await operator.on_operator_button(event, ctx)
        self.assertFalse(ctx.bot_data.get('progress_state'))
        event.callback_query.message.message_id = 999
        ctx.bot.get_chat_member.return_value = N(status='administrator')
        await operator.on_operator_button(event, ctx)
        self.assertFalse(ctx.bot_data.get('progress_state'))
        self.assertEqual(record['kb_msg_id'], 20)

    def test_review_stage_stays_review_and_forgetting_removes_uuid_alias(self):
        ctx, record, _ = self.setup_record(stage='other')
        migrate_records(ctx.bot_data)
        self.assertEqual(record['queue_kind'], 'otherpark')
        self.assertTrue(operator.is_review_record(record))
        operator._forget_application(ctx, (-1001, 20), record)
        self.assertFalse(ctx.bot_data['app_messages'])
        self.assertFalse(ctx.bot_data['applications'])

    def test_pending_legacy_transfer_is_not_reinterpreted(self):
        ctx, record, _ = self.setup_record()
        record['pending_cleanup'] = {'group_chat_id': -999, 'photo_msg_ids': [1], 'kb_msg_id': 2}
        migrate_records(ctx.bot_data)
        self.assertFalse(ctx.bot_data['applications'])
        self.assertNotIn('applicant_id', record)

    async def test_pending_cleanup_resumes_without_duplicate_copy(self):
        ctx, record, event = self.setup_record(stage='incomplete')
        record['pending_cleanup'] = {'group_chat_id': -1001, 'photo_msg_ids': [21, 22], 'kb_msg_id': 20}
        record.update(group_chat_id=-1002, kb_msg_id=30, photo_msg_ids=[31, 32])
        ctx.bot.delete_message = AsyncMock()
        ctx.bot.copy_messages = AsyncMock()
        ctx.bot.send_message = AsyncMock()
        ctx.application = N(update_persistence=AsyncMock(), persistence=N(flush=AsyncMock()))
        await operator.on_operator_button(event, ctx)
        self.assertNotIn('pending_cleanup', record)
        ctx.bot.copy_messages.assert_not_awaited()
        self.assertEqual(ctx.bot.delete_message.await_count, 3)
        self.assertIs(ctx.bot_data['applications'][(-1002, 30)], record)
        self.assertTrue(operator.is_review_record(record))

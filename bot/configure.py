"""Read/validate group routes without displaying bot credentials."""
import argparse
import asyncio
import os
import re
from bot.route_settings import ROUTE_KEYS, destination, save_settings


def problems():
    seen, errors = {}, []
    for key in sorted(ROUTE_KEYS):
        value = destination(key)
        if not re.fullmatch(r'-[1-9][0-9]*', value):
            errors.append(f'{key}: guruh ID sozlanmagan')
        elif value in seen:
            errors.append(f'{key}: {seen[value]} bilan bir xil guruh')
        else:
            seen[value] = key
    return errors


async def telegram_check():
    from telegram import Bot
    from telegram.error import NetworkError, TimedOut
    from telegram.request import HTTPXRequest
    if not os.environ.get('TELEGRAM_BOT_TOKEN'):
        print('Token muhitda topilmadi; xizmatning EnvironmentFile sozlamasini yuklang.')
        return 1
    for attempt in range(1, 4):
        try:
            request = HTTPXRequest(connect_timeout=15, read_timeout=30,
                                   write_timeout=30, pool_timeout=15)
            async with Bot(os.environ['TELEGRAM_BOT_TOKEN'], request=request) as bot:
                me = await bot.get_me()
                print('Bot: @' + me.username)
                failed = False
                for key in sorted(ROUTE_KEYS):
                    for group_attempt in range(2):
                        try:
                            chat = await bot.get_chat(int(destination(key)))
                            member = await bot.get_chat_member(chat.id, me.id)
                            if chat.type not in ('group', 'supergroup'):
                                raise ValueError('Guruh ID kerak')
                            if member.status not in ('administrator', 'creator'):
                                raise ValueError('Botni administrator qiling')
                            if key not in ('BRAND_GROUP', 'SPECTRE_GROUP') and member.status != 'creator' and not member.can_delete_messages:
                                raise ValueError('Xabarlarni o‘chirish huquqi kerak')
                            print(key + ': OK')
                            break
                        except (NetworkError, TimedOut) as error:
                            if group_attempt == 0:
                                await asyncio.sleep(2)
                                continue
                            print(key + ': ' + type(error).__name__)
                            failed = True
                        except Exception as error:
                            print(key + ': ' + (str(error) if isinstance(error, ValueError) else type(error).__name__))
                            failed = True
                            break
                return int(failed)
        except (NetworkError, TimedOut) as error:
            print(f'Telegram getMe urinishi {attempt}/3: {type(error).__name__}')
            if attempt == 3:
                return 1
            await asyncio.sleep(3)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['show', 'check', 'set'])
    parser.add_argument('--offline', action='store_true')
    for key in sorted(ROUTE_KEYS):
        parser.add_argument('--' + key.lower(), dest=key)
    args = parser.parse_args(argv)
    if args.action == 'set':
        changes = {key: getattr(args, key) for key in ROUTE_KEYS if getattr(args, key) is not None}
        if not changes:
            parser.error('Kamida bitta guruh ID kiriting.')
        save_settings(changes)
        print('Guruhlar saqlandi.')
        return 0
    if args.action == 'show':
        for key in sorted(ROUTE_KEYS):
            print(key + ': ' + (destination(key) or 'sozlanmagan'))
        return 0
    errors = problems()
    for error in errors:
        print(error)
    if errors:
        return 1
    if args.offline:
        print('SALOM guruhlari to‘liq va alohida.')
        return 0
    try:
        return asyncio.run(telegram_check())
    except Exception as error:
        print('Telegram tekshiruvi tugamadi: ' + type(error).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

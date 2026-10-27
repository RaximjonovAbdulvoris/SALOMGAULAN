from types import SimpleNamespace as N
from unittest.mock import AsyncMock

def context(region=None):
    return N(
        user_data={"region": region} if region else {},
        bot_data={},
        bot=N(
            get_chat_member=AsyncMock(return_value=N(status="member")),
            send_message=AsyncMock(return_value=N(message_id=90)),
            send_media_group=AsyncMock(return_value=[N(message_id=80), N(message_id=81)]),
        ),
    )


def update(text=""):
    message = N(
        text=text, message_id=1, reply_text=AsyncMock(), reply_photo=AsyncMock(),
        contact=None,
    )
    return N(
        message=message, effective_message=message, callback_query=None,
        effective_chat=N(id=123, type="private"),
        effective_user=N(id=123, full_name="Test Applicant", username="test_applicant"),
    )


def callback(data):
    result = update()
    result.callback_query = N(
        data=data, message=result.message, answer=AsyncMock(),
        edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock(),
    )
    return result



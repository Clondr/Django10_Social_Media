from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Notice, SettingForNotice


def notifications_enabled(profile, setting_name):
    settings = SettingForNotice.objects.filter(user=profile).first()
    return settings is None or getattr(settings, setting_name)


def create_notice(recipient, message, type_notice, request_for_friendship=None):
    notice = Notice.objects.create(
        recipient=recipient,
        message=message,
        type_notice=type_notice,
        request_for_friendship=request_for_friendship,
    )
    broadcast_notice(notice)
    return notice


def broadcast_notice(notice):
    channel_layer = get_channel_layer()
    unread_count = Notice.objects.filter(
        recipient=notice.recipient,
        is_read=False,
    ).count()
    async_to_sync(channel_layer.group_send)(
        f"notifications_{notice.recipient_id}",
        {
            "type": "notification.created",
            "notification": {
                "id": notice.id,
                "message": notice.message,
                "type_notice": notice.type_notice,
                "unread_count": unread_count,
            },
        },
    )


def broadcast_notice_count(profile):
    channel_layer = get_channel_layer()
    unread_count = Notice.objects.filter(recipient=profile, is_read=False).count()
    async_to_sync(channel_layer.group_send)(
        f"notifications_{profile.id}",
        {
            "type": "notification.count",
            "unread_count": unread_count,
        },
    )


def get_unread_notice_count(request):
    if not request.user.is_authenticated:
        return {"unread_notice_count": 0}
    return {
        "unread_notice_count": Notice.objects.filter(
            recipient__user=request.user,
            is_read=False,
        ).count()
    }

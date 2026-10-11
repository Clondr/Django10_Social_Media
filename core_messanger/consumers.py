import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


@database_sync_to_async
def get_profile_id(user):
    from core_profile.models import Profile

    return Profile.objects.filter(user=user).values_list("id", flat=True).first()


@database_sync_to_async
def get_user_profile(user):
    return user.profile


logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4003)
            return

        profile_id = await get_profile_id(user)
        if profile_id is None:
            await self.close(code=4003)
            return

        self.group_name = f"notifications_{profile_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        unread_count = await self.get_unread_notice_count(user)
        await self.send(text_data=json.dumps({
            "type": "notification.count",
            "unread_count": unread_count,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        await self.close(code=1008)

    async def notification_created(self, event):
        await self.send(text_data=json.dumps({
            "type": "notification.created",
            "notification": event["notification"],
        }))

    async def notification_count(self, event):
        await self.send(text_data=json.dumps({
            "type": "notification.count",
            "unread_count": event["unread_count"],
        }))

    @database_sync_to_async
    def get_unread_notice_count(self, user):
        from core_profile.models import Notice

        return Notice.objects.filter(recipient__user=user, is_read=False).count()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]
        self.group_name = f"chat_{self.chat_id}"
        self.profile = await get_user_profile(self.user)

        # Пускаем только участников чата
        try:
            ok = self.user.is_authenticated and await self.is_participant()
        except Exception:
            logger.exception("connect check failed for chat %s", self.chat_id)
            ok = False
        if not ok:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.broadcast_presence("online")

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.broadcast_presence("offline")
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data)
        except (TypeError, json.JSONDecodeError):
            await self.send(text_data=json.dumps({"error": "invalid json"}))
            return

        data_type = data.get("type")
        if data_type == "typing":
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.typing",
                    "user_id": self.profile.id,
                    "username": self.user.username,
                    "is_typing": bool(data.get("is_typing", False)),
                },
            )
            return

        if data_type == "presence":
            await self.broadcast_presence(data.get("status", "online"))
            return

        try:
            message = await self.save_message(
                ciphertext=data.get("ciphertext", ""),
                nonce=data.get("nonce", ""),
                sender_public_key=data.get("sender_public_key", ""),
                self_ciphertext=data.get("self_ciphertext", ""),
                self_nonce=data.get("self_nonce", ""),
            )
        except Exception:
            logger.exception("save_message failed for chat %s", self.chat_id)
            await self.send(text_data=json.dumps({"error": "could not save message"}))
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.message",
                "message": {
                    "id": message.id,
                    "ciphertext": message.ciphertext,
                    "nonce": message.nonce,
                    "sender_public_key": message.sender_public_key,
                    "sender_id": message.sender_id,
                    "self_ciphertext": message.self_ciphertext or "",
                    "self_nonce": message.self_nonce or "",
                    "sender": message.sender.user.username,
                    "sender_avatar": message.sender.avatar.url,
                    "timestamp": message.timestamp.strftime("%H:%M %d.%m.%Y"),
                },
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    async def chat_typing(self, event):
        await self.send(text_data=json.dumps({
            "type": "typing",
            "user_id": event["user_id"],
            "username": event["username"],
            "is_typing": event["is_typing"],
        }))

    async def chat_presence(self, event):
        await self.send(text_data=json.dumps({
            "type": "presence",
            "user_id": event["user_id"],
            "username": event["username"],
            "status": event["status"],
        }))

    async def broadcast_presence(self, status):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.presence",
                "user_id": self.profile.id,
                "username": self.user.username,
                "status": status,
            },
        )

    @database_sync_to_async
    def is_participant(self):
        from .models import Chat

        return Chat.objects.filter(id=self.chat_id, participants__user=self.user).exists()

    @database_sync_to_async
    def save_message(self, ciphertext, nonce, sender_public_key, self_ciphertext="", self_nonce=""):
        from .models import Chat, Message
        from core_profile.notifications import create_notice

        if not ciphertext or not nonce:
            raise ValueError("ciphertext and nonce are required")

        sender = self.user.profile
        chat = Chat.objects.get(id=self.chat_id, participants=sender)
        recipient = chat.get_other_participant(sender)
        if recipient is None:
            raise ValueError("no recipient in chat")
        message = Message.objects.create(
            sender=sender,
            recipient=recipient,
            ciphertext=ciphertext,
            nonce=nonce,
            sender_public_key=sender_public_key,
            self_ciphertext=self_ciphertext,
            self_nonce=self_nonce,
        )
        chat.messages.add(message)
        for recipient in chat.participants.exclude(id=sender.id):
            create_notice(
                recipient,
                f'Новое сообщение от {sender.user.username}.',
                'message',
            )
        return message


class PostReactionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.post_id = self.scope["url_route"]["kwargs"]["post_id"]
        self.group_name = f"post_reactions_{self.post_id}"

        if not self.user.is_authenticated:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def reaction_update(self, event):
        await self.send(text_data=json.dumps(event["reaction"]))

import json
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import *
from core_profile.models import *
from django.db.models import Prefetch
from core_profile.notifications import (
    broadcast_notice_count,
    create_notice,
    notifications_enabled,
)
from django.utils import timezone
# Create your views here.


def get_chat_creator(chat):
    relation = chat.participants.through.objects.filter(
        chat_id=chat.id
    ).order_by('id').first()
    return relation.profile if relation else None


@login_required
def chat_view(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    if request.user.profile not in chat.participants.all():
        return redirect('home')  # Redirect if the user is not a participant

    messages = chat.messages.order_by('timestamp')
    for message in messages:
        message.file_kind = get_file_kind(message.file)
    other_participant = chat.get_other_participant(request.user.profile)
    participants = chat.participants.all().order_by('user__username')
    available_participants = Profile.objects.exclude(
        user=request.user
    ).exclude(
        id__in=chat.participants.values_list('id', flat=True)
    ).order_by('user__username')
    creator = get_chat_creator(chat)
    files = None
    return render(request, 'core_messanger/chat_view.html', {
        'chat': chat,
        'chat_messages': messages,
        'file': files,
        'other_participant': other_participant,
        'recipient_public_key': (other_participant or request.user.profile).encryption_public_key,
        'participants': participants,
        'available_participants': available_participants,
        'creator': creator,
        'can_manage_participants': request.user.profile == creator,
        'can_leave_group': participants.count() > 2,
    })


def get_file_kind(file):
    """Определяет тип вложения по расширению файла."""
    if not file:
        return None
    name = file.name.lower()
    image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg')
    video_exts = ('.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv')
    audio_exts = ('.mp3', '.wav', '.ogg', '.m4a', '.flac')
    if name.endswith(image_exts):
        return 'image'
    if name.endswith(video_exts):
        return 'video'
    if name.endswith(audio_exts):
        return 'audio'
    return 'other'


@login_required
def create_chat(request, recipient_id):
    recipient = get_object_or_404(Profile, id=recipient_id)
    chat = Chat.objects.filter(
        participants=request.user.profile,
    ).filter(
        participants=recipient,
    ).annotate(
        participant_count=Count('participants', distinct=True),
    ).filter(
        participant_count=2,
    ).order_by('id').first()
    if chat is None:
        chat = Chat.objects.create()
        chat.participants.add(request.user.profile, recipient)
    return redirect('chat-view', chat_id=chat.id)

@login_required
def chat_list_view(request):
    chats = Chat.objects.filter(participants=request.user.profile).annotate(
        participant_count=Count('participants')
    ).prefetch_related(
        Prefetch('participants', queryset=Profile.objects.select_related('user'))
    )
    for chat in chats:
        # Compute other_participant and group_participants from prefetched participants
        other_participant = None
        group_participants = []
        for participant in chat.participants.all():
            if participant.id == request.user.profile.id:
                continue
            if other_participant is None:
                other_participant = participant
            else:
                group_participants.append(participant)
        chat.other_participant = other_participant
        chat.group_participants = group_participants
    return render(request, 'core_messanger/chat_list.html', {'chats': chats})

@login_required
def send_message(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    if request.user.profile not in chat.participants.all():
        return redirect('home')  # Redirect if the user is not a participant

    if request.method == 'POST':
        ciphertext = request.POST.get('ciphertext')
        file = request.FILES.get('file')
        nonce = request.POST.get('nonce')
        self_ciphertext = request.POST.get('self_ciphertext') or ''
        self_nonce = request.POST.get('self_nonce') or ''
        public_key = request.POST.get('public_key') or request.user.profile.encryption_public_key
        try:
            public_key_data = json.loads(public_key)
        except (TypeError, json.JSONDecodeError):
            public_key_data = None
        if (
            not ciphertext
            or not nonce
            or not isinstance(public_key_data, dict)
            or public_key_data.get('kty') != 'EC'
            or public_key_data.get('crv') != 'P-256'
            or not public_key_data.get('x')
            or not public_key_data.get('y')
        ):
            return HttpResponseBadRequest('Encrypted message and public key are required')
        public_key = json.dumps(public_key_data, separators=(',', ':'))
        if public_key != request.user.profile.encryption_public_key:
            request.user.profile.encryption_public_key = public_key
            request.user.profile.save(update_fields=['encryption_public_key'])
        message = Message.objects.create(
            sender=request.user.profile,
            recipient=chat.get_other_participant(request.user.profile),
            ciphertext=ciphertext,
            nonce=nonce,
            file=file,
            sender_public_key=public_key,
            self_ciphertext=self_ciphertext,
            self_nonce=self_nonce,
        )
        chat.messages.add(message)
        for recipient in chat.participants.exclude(id=request.user.profile.id):
            create_notice(
                recipient,
                f'Новое сообщение от {request.user.username}.',
                'message',
            )

    return redirect('chat-view', chat_id=chat.id)

@login_required
def delete_message(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    chat = message.chats.first()
    if chat is None:
        return redirect('chat-list-view')

    if request.user.profile not in chat.participants.all():
        return redirect('home')

    creator = get_chat_creator(chat)
    is_sender = request.user.profile == message.sender
    is_chat_creator = request.user.profile == creator

    if not (is_sender or is_chat_creator):
        return redirect('chat-view', chat_id=chat.id)

    message.delete()
    return redirect('chat-view', chat_id=chat.id)

@login_required
def delete_chat(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    if request.user.profile in chat.participants.all():
        # Удаляем все сообщения и сам чат в рамках атомарной транзакции
        with transaction.atomic():
            chat.messages.all().delete()
            chat.delete()
    return redirect('chat-list-view')

@login_required
def edit_message(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    if request.user.profile != message.sender:
        return redirect('home')  # Redirect if the user is not the sender
    chat = message.chats.first()
    if chat is None:
        return redirect('chat-list-view')

    if request.method == 'POST':
        ciphertext = request.POST.get('ciphertext')
        nonce = request.POST.get('nonce')
        if not ciphertext or not nonce:
            return HttpResponseBadRequest('Encrypted message is required')
        message.ciphertext = ciphertext
        message.nonce = nonce
        message.self_ciphertext = request.POST.get('self_ciphertext') or ''
        message.self_nonce = request.POST.get('self_nonce') or ''
        message.save(update_fields=['ciphertext', 'nonce', 'self_ciphertext', 'self_nonce'])
        return redirect('chat-view', chat_id=chat.id)

    other_participant = chat.get_other_participant(request.user.profile)
    return render(request, 'core_messanger/edit_message.html', {
        'message': message,
        'recipient_public_key': other_participant.encryption_public_key,
    })


@login_required
def chat_recipient_public_key(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    if request.user.profile not in chat.participants.all():
        return JsonResponse({'ok': False, 'error': 'not a participant'}, status=403)

    recipient = chat.get_other_participant(request.user.profile)
    return JsonResponse({
        'ok': True,
        'public_key': recipient.encryption_public_key if recipient else '',
    })


@login_required
@require_POST
def register_public_key(request):
    try:
        public_key = json.loads(request.POST.get('public_key', ''))
    except (TypeError, json.JSONDecodeError):
        return HttpResponseBadRequest('Invalid public key')

    if (
        not isinstance(public_key, dict)
        or public_key.get('kty') != 'EC'
        or public_key.get('crv') != 'P-256'
        or not public_key.get('x')
        or not public_key.get('y')
    ):
        return HttpResponseBadRequest('Invalid public key')

    request.user.profile.encryption_public_key = json.dumps(public_key, separators=(',', ':'))
    request.user.profile.save(update_fields=['encryption_public_key'])
    return JsonResponse({'ok': True})

@login_required
def show_info_about_message(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    return render(request, 'core_messanger/message_info.html', {'message': message})

@login_required
def search_user_for_chat(request):
    query = request.GET.get('q')
    if query:
        users = Profile.objects.filter(user__username__icontains=query).exclude(user=request.user)
    else:
        users = Profile.objects.none()
    return render(request, 'core_messanger/search_user.html', {'users': users})

@login_required
def add_participant_to_chat(request, chat_id=None, participant_id=None):
    # Get IDs from URL parameters or request GET/POST data
    chat_id = chat_id or request.GET.get('chat_id') or request.POST.get('chat_id')
    participant_id = participant_id or request.GET.get('participant_id') or request.POST.get('participant_id')
    
    # Если параметры не предоставлены, показываем форму для их выбора
    if not chat_id:
        return HttpResponseBadRequest('Chat is required')

    chat = get_object_or_404(Chat, id=chat_id)
    creator = get_chat_creator(chat)
    if request.user.profile != creator:
        return HttpResponseForbidden('Only the chat creator can manage participants')

    if not participant_id:
        users = Profile.objects.exclude(
            user=request.user
        ).exclude(
            id__in=chat.participants.values_list('id', flat=True)
        ).order_by('user__username')
        return render(request, 'core_messanger/add_participant_to_chat.html', {
            'chat': chat,
            'users': users,
        })
    
    # Если параметры предоставлены, обрабатываем добавление участника
    participant = get_object_or_404(Profile, id=participant_id)
    
    # Проверяем, что участник уже не в чате
    if participant in chat.participants.all():
        return HttpResponseBadRequest('This user is already a participant of this chat')
    
    chat.participants.add(participant)
    return redirect('chat-view', chat_id=chat.id)


@login_required
@require_POST
def remove_participant_from_chat(request, chat_id, participant_id):
    chat = get_object_or_404(Chat, id=chat_id)
    creator = get_chat_creator(chat)
    if request.user.profile != creator:
        return HttpResponseForbidden('Only the chat creator can manage participants')

    participant = get_object_or_404(Profile, id=participant_id)
    if participant == creator:
        return HttpResponseBadRequest('The chat creator cannot be removed')

    if not chat.participants.filter(id=participant.id).exists():
        return HttpResponseBadRequest('This user is not a participant of this chat')

    with transaction.atomic():
        chat.participants.remove(participant)
        if chat.participants.count() == 1:
            chat.messages.all().delete()
            chat.delete()
            return redirect('chat-list-view')

    return redirect('chat-view', chat_id=chat.id)


@login_required
@require_POST
def leave_chat(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    profile = request.user.profile

    if not chat.participants.filter(id=profile.id).exists():
        return HttpResponseForbidden('You are not a participant of this chat')

    with transaction.atomic():
        chat.participants.remove(profile)
        if chat.participants.count() == 1:
            chat.messages.all().delete()
            chat.delete()

    return redirect('chat-list-view')

@login_required
def request_for_friendship(request, recipient_id):
    recipient = get_object_or_404(Profile, id=recipient_id)
    if recipient == request.user.profile:
        return HttpResponseBadRequest('You cannot send a friend request to yourself')

    existing_request = FriendRequest.objects.filter(sender=request.user.profile, recipient=recipient).first()
    if existing_request:
        return HttpResponseBadRequest('Friend request already sent')

    if request.user.profile.friends.filter(id=recipient.id).exists():
        return HttpResponseBadRequest('You are already friends with this user')

    friend_request = FriendRequest.objects.create(sender=request.user.profile, recipient=recipient)
    if notifications_enabled(recipient, 'receive_friend_request_notifications'):
        create_notice(
            recipient,
            f'Новый запрос в друзья от {request.user.username}.',
            'friend_request',
            request_for_friendship=friend_request,
        )
    return redirect('profile-view', id=recipient.id)

@login_required
def accept_friend_request(request, request_id):
    friend_request = get_object_or_404(FriendRequest, id=request_id)
    if friend_request.recipient != request.user.profile:
        return HttpResponseForbidden('You are not authorized to accept this friend request')

    if friend_request.sender.friends.filter(id=friend_request.recipient.id).exists():
        Notice.objects.filter(request_for_friendship=friend_request).delete()
        broadcast_notice_count(friend_request.recipient)
        messages.warning(request, 'Цей користувач вже у вас в друзях.')
        return redirect('profile')

    with transaction.atomic():
        friend_request.is_accepted = True
        friend_request.when_was_accepted = timezone.now()
        friend_request.save(update_fields=['is_accepted', 'when_was_accepted'])
        friend_request.sender.friends.add(friend_request.recipient)
        Notice.objects.filter(request_for_friendship=friend_request).delete()

    broadcast_notice_count(friend_request.recipient)
    return redirect('profile-view', id=friend_request.sender.id)

@login_required
def decline_friend_request(request, request_id):
    friend_request = get_object_or_404(FriendRequest, id=request_id)
    if friend_request.recipient != request.user.profile:
        return HttpResponseForbidden('You are not authorized to decline this friend request')

    Notice.objects.filter(request_for_friendship=friend_request).delete()
    broadcast_notice_count(friend_request.recipient)
    friend_request.delete()
    return redirect('profile-view', id=friend_request.sender.id)

@login_required
def remove_friend(request, friend_id):
    friend = get_object_or_404(Profile, id=friend_id)
    if not request.user.profile.friends.filter(id=friend.id).exists():
        return HttpResponseBadRequest('You are not friends with this user')
    request.user.profile.friends.remove(friend)
    return redirect('profile-view', id=friend.id)

@login_required
def all_notices(request):
    notices = Notice.objects.filter(recipient=request.user.profile).order_by('-created_at')
    return render(request, 'core_messanger/all_notices.html', {'notices': notices})

@login_required
@require_POST
def mark_notice_as_read(request, notice_id):
    notice = get_object_or_404(Notice, id=notice_id, recipient=request.user.profile)
    notice.is_read = True
    notice.save(update_fields=['is_read'])
    broadcast_notice_count(request.user.profile)
    return redirect('all-notices')

@login_required
@require_POST
def delete_notice(request, notice_id):
    notice = get_object_or_404(Notice, id=notice_id, recipient=request.user.profile)
    notice.delete()
    broadcast_notice_count(request.user.profile)
    return redirect('all-notices')
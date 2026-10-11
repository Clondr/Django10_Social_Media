from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import *
from .forms import *
# Create your views here.

@login_required
def profile_view(request, id=None):
    if id is None:
        id = request.user.id
        profile = get_object_or_404(Profile, user_id=id)
        pending_friend_requests = profile.received_friend_requests.filter(
            is_accepted=False
        ).select_related('sender__user').order_by('-created_at')
        notices = profile.notices.select_related('request_for_friendship__sender__user').order_by('-created_at')
        return render(request, 'core_profile/profile.html', {
            'profile': profile,
            'pending_friend_requests': pending_friend_requests,
            'notices': notices,
        })
    else:
        profile = get_object_or_404(Profile, user_id=id)
        return render(request, 'core_profile/stranger_profile.html', {'profile': profile})

@login_required
def edit_profile_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        if 'reset_avatar' in request.POST:
            profile.avatar = Profile._meta.get_field('avatar').default
            profile.save(update_fields=['avatar'])
            return redirect('edit-profile')

        form = UploadAvatarForm(request.POST, request.FILES, instance=profile)
        new_first_name = request.POST.get('first_name')
        if new_first_name is not None:
            request.user.first_name = new_first_name
            request.user.save()
        new_last_name = request.POST.get('last_name')
        if new_last_name is not None:
            request.user.last_name = new_last_name
            request.user.save()
        new_bio = request.POST.get('bio')
        if new_bio is not None:
            profile.bio = new_bio
            profile.save()
        new_avatar = request.FILES.get('avatar')
        if new_avatar is not None:
            profile.avatar = new_avatar
            profile.save()
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = UploadAvatarForm(instance=profile)
    return render(request, 'core_profile/edit_profile.html', {'form': form})

@login_required
def delete_bio_of_user(request):
    profile = get_object_or_404(Profile, user=request.user)
    profile.bio = ''
    profile.save()
    return redirect('profile')

@login_required
def change_settings(request):
    setting, _ = SettingForNotice.objects.get_or_create(user=request.user.profile)
    if request.method == 'POST':
        form = ChangeSettingsForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = ChangeSettingsForm(instance=setting)
    return render(request, 'core_profile/change_settings.html', {'form': form})
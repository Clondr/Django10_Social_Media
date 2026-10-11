from django import forms
from .models import Profile, SettingForNotice

class UploadAvatarForm(forms.ModelForm):
    avatar = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
    )
    class Meta:
        model = Profile
        fields = ['avatar']
        labels = {'avatar': 'Завантажити аватар'}

class ChangeSettingsForm(forms.ModelForm):
    receive_subscription_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    receive_friend_request_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    receive_administration_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    receive_other_notifications = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    class Meta:
        model = SettingForNotice
        fields = ['receive_subscription_notifications', 
                'receive_friend_request_notifications', 
                'receive_administration_notifications',
                'receive_other_notifications']

        labels = {'receive_subscription_notifications': 'Отримувати сповіщення про підписки',
                'receive_friend_request_notifications': 'Отримувати сповіщення про запити на дружбу',
                'receive_administration_notifications': 'Отримувати сповіщення про адміністрування',
                'receive_other_notifications': 'Отримувати інші сповіщення'}
from django.db import models
from django.db.models.signals import post_save 
from django.dispatch import receiver 

# Create your models here.
@receiver (post_save ,sender ='auth.User')
def save_user_profile (sender ,instance ,created ,**kwargs ):
    if created :
        Profile .objects .create (user =instance )
    else :
        if hasattr (instance ,'profile'):
            instance .profile .save ()

class Profile(models.Model):
    USER ='user'
    ADMIN ='admin'
    ROLE_CHOICES =[
    (USER ,'User'),
    (ADMIN ,'Admin'),
    ]
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    role = models.CharField(max_length=5, choices=ROLE_CHOICES, default=USER)
    bio = models.TextField(blank=True, max_length=250)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, default='avatars/default.png' )
    encryption_public_key = models.TextField(blank=True)
    friends = models.ManyToManyField('self', symmetrical=True, blank=True)

    def __str__(self):
        return f'Profile of {self.user.username} role: {self.role}'

    def _sync_role_from_user(self):
        if self.user_id:
            if self.user.is_superuser:
                self.role = self.ADMIN
            else:
                self.role = self.USER

    def save(self, *args, **kwargs):
        self._sync_role_from_user()
        super().save(*args, **kwargs)

    def auto_give_role(self):
        self._sync_role_from_user()
        self.save()

class Friendship(models.Model):
    user1 = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='friendships')
    user2 = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='friendships_as_user2')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user1', 'user2')

    def __str__(self):
        return f'{self.user1.username} -> {self.user2.username}'

class FriendRequest(models.Model):
    sender = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='sent_friend_requests')
    recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='received_friend_requests')
    created_at = models.DateTimeField(auto_now_add=True)
    is_accepted = models.BooleanField(default=False)
    when_was_accepted = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('sender', 'recipient')

    def __str__(self):
        return f'Friend request from {self.sender.username} to {self.recipient.username}'


class Notice(models.Model):
    TYPES_NOTICE = [
        ('friend_request', 'Friend Request'),
        ('message', 'Message'),
        ('subscription', 'Subscription'),
        ('administration', 'Administration'),
        ('other', 'Other'),
        # Add more types as needed
    ]
    recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='notices')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    request_for_friendship = models.ForeignKey(FriendRequest, on_delete=models.CASCADE, null=True, blank=True, related_name='notices')
    type_notice = models.CharField(max_length=50, choices=TYPES_NOTICE, default='friend_request')  # 'friend_request', 'message', etc.

    def __str__(self):
        return f'Notice for {self.recipient.username}: {self.message[:20]}...'
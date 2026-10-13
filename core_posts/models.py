from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

# Create your models here.
class Comment(models.Model):
    author = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.content[:25]  # Return the first 25 characters of the comment

class Post(models.Model):
    author = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    content = models.TextField()
    file = models.FileField(upload_to='post_files/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    comments = models.ManyToManyField(Comment, related_name='post_comments', blank=True)

    def __str__(self):
        return self.title

    @property
    def file_kind(self):
        """Determine the attachment type based on file extension."""
        if not self.file:
            return None
        name = self.file.name.lower()
        image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico')
        video_exts = ('.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv')
        audio_exts = ('.mp3', '.wav', '.ogg', '.m4a', '.flac', '.opus')
        if name.endswith(image_exts):
            return 'image'
        if name.endswith(video_exts):
            return 'video'
        if name.endswith(audio_exts):
            return 'audio'
        return 'document'

    def save(self, *args, **kwargs):
        old_file_name = None
        if self.pk:
            old_file_name = type(self).objects.filter(pk=self.pk).values_list('file', flat=True).first()

        super().save(*args, **kwargs)

        if old_file_name and old_file_name != self.file.name:
            self.file.storage.delete(old_file_name)

    def only_one_comment_on_user(self, user):
        """
        Check if the user has already commented on this post.
        Returns True if the user has commented, False otherwise.
        """
        return self.comments.filter(author=user).exists()

@receiver(post_delete)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """Удаляет прикрепленный файл при удалении любого объекта модели."""
    file_field = getattr(instance, 'file', None)
    if file_field and file_field.name:
        file_field.delete(save=False)

class Reaction(models.Model):
    REACTION_CHOICES = [
        ('like', 'Like'),
        ('dislike', 'Dislike'),
    ]
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='reactions')
    reaction_type = models.CharField(max_length=10, choices=REACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')  # Ensure a user can react only once per post

    def __str__(self):
        return f"{self.user.username} reacted with {self.reaction_type} to {self.post.title}"

class Subscription(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='subscribers')
    follower = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='following')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ('user', 'follower')  # Ensure a follower can subscripbe only once per user

    def __str__(self):
        return f"{self.follower.username} is following {self.user.username}"

class News(models.Model):
    author = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='news_files/', blank=True, null=True)

    def __str__(self):
        return self.title

    @property
    def file_kind(self):
        """Determine the attachment type based on file extension."""
        if not self.file:
            return None
        name = self.file.name.lower()
        image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico')
        video_exts = ('.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv')
        audio_exts = ('.mp3', '.wav', '.ogg', '.m4a', '.flac', '.opus')
        if name.endswith(image_exts):
            return 'image'
        if name.endswith(video_exts):
            return 'video'
        if name.endswith(audio_exts):
            return 'audio'
        return 'document'

    def save(self, *args, **kwargs):
        old_file_name = None
        if self.pk:
            old_file_name = type(self).objects.filter(pk=self.pk).values_list('file', flat=True).first()

        super().save(*args, **kwargs)

        if old_file_name and old_file_name != self.file.name:
            self.file.storage.delete(old_file_name)
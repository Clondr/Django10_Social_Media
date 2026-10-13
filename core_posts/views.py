from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Prefetch, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.http import Http404
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Post, Comment, Reaction, Subscription, News
from .forms import PostForm, CommentForm
from django.contrib.auth.models import User
from core_profile.notifications import create_notice, notifications_enabled
# Create your views here.


def post_list(request):
    search_query = request.GET.get('q', '').strip()
    if search_query:
        posts = Post.objects.filter(
            Q(title__icontains=search_query)
            | Q(content__icontains=search_query)
            | Q(author__username__icontains=search_query)
        ).distinct().select_related('author', 'author__profile').order_by('-created_at')
    else:
        posts = Post.objects.all().select_related('author', 'author__profile').order_by('-created_at')
    return render(request, 'core_posts/post_list.html', {
        'posts': posts,
        'search_query': search_query,
    })


def post_detail(request, post_id):
    # Logic to retrieve and display a specific post by its ID
    post = get_object_or_404(Post.objects.select_related('author', 'author__profile').prefetch_related(
        Prefetch('comments', queryset=Comment.objects.select_related('author', 'author__profile'))
    ).annotate(
        like_count=Count('reactions', filter=Q(reactions__reaction_type='like')),
        dislike_count=Count('reactions', filter=Q(reactions__reaction_type='dislike'))
    ), id=post_id)
    user_reaction = None
    if request.user.is_authenticated:
        user_reaction = post.reactions.filter(
            user=request.user
        ).values_list('reaction_type', flat=True).first()
    return render(request, 'core_posts/post_detail.html', {
        'post': post,
        'file_kind': post.file_kind,
        'reaction_counts': {
            'like': post.like_count,
            'dislike': post.dislike_count,
        },
        'user_reaction': user_reaction,
    })


@login_required
def create_post(request):
    if request.method == 'POST':
        # Logic to handle post creation
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            return redirect('post_detail', post_id=post.id)
    else:
        form = PostForm()
    return render(request, 'core_posts/create_post.html', {'form': form})


@login_required
def delete_post(request, post_id):
    # Logic to delete a specific post by its ID
    post = get_object_or_404(Post, id=post_id)
    if request.user.profile.role == 'admin':
        if request.method == 'POST':
            post.delete()
            if notifications_enabled(post.author.profile, 'receive_administration_notifications'):
                create_notice(
                    post.author.profile,
                    f'Ваш пост був «{post.title}» видален адміністратором.',
                    'administration',
                )
            return redirect('post_list')
        return render(request, 'core_posts/confirm_delete.html', {'post': post})
    elif request.user == post.author:
        if request.method == 'POST':
            post.delete()
            return redirect('post_list')
        return render(request, 'core_posts/confirm_delete.html', {'post': post})
    else:
        return redirect('home')


@login_required
@require_POST
def delete_post_attachment(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if (
        request.user != post.author
        and not request.user.is_superuser
        and request.user.profile.role != 'admin'
    ):
        return redirect('home')
    if request.user.profile.role == 'admin':
        if post.file:
            post.file = None
            if notifications_enabled(post.author.profile, 'receive_administration_notifications'):
                create_notice(
                    post.author.profile,
                    f'З вашого поста «{post.title}» адміністратор видалив вложення.',
                    'administration',
                )
            post.save()

    elif request.user == post.author:
        if post.file:
            post.file = None
            post.save()
    return redirect('post_detail', post_id=post.id)


@login_required
@require_POST
def delete_news_attachment(request, news_id):
    news = get_object_or_404(News, id=news_id)
    if (
        request.user != news.author
        and not request.user.is_superuser
        and request.user.profile.role != 'admin'
    ):
        return redirect('home')

    if news.file:
        news.file = None
        news.save()
    return redirect('news_detail', news_id=news.id)


@login_required
def edit_post(request, post_id):
    # Logic to edit a specific post by its ID
    post = get_object_or_404(Post, id=post_id)
    if request.user.profile.role == 'admin' or request.user == post.author:
        if request.method == 'POST':
            form = PostForm(request.POST, request.FILES, instance=post)
            if form.is_valid():
                form.save()
                return redirect('post_detail', post_id=post.id)
        else:
            form = PostForm(instance=post)
        return render(request, 'core_posts/edit_post.html', {'form': form, 'post': post})


@login_required
def create_comment(request, post_id):
    # Logic to handle comment creation for a specific post
    form = CommentForm(request.POST or None)
    post = get_object_or_404(Post, id=post_id)
    if request.user == post.author:
        return render(request, 'core_posts/create_comment.html', {'post': post, 'error': 'You cannot comment on your own post.'})
    else:
        if post.only_one_comment_on_user(request.user):
            return render(request, 'core_posts/create_comment.html', {'post': post, 'error': 'You have already commented on this post.'})
        if request.method == 'POST':
            content = request.POST.get('content')
            if content:
                comment = Comment.objects.create(author=request.user, content=content)
                post.comments.add(comment)
                return redirect('post_detail', post_id=post.id)
        return render(request, 'core_posts/create_comment.html', {'post': post, 'form': form})


@login_required
def delete_comment(request, post_id, comment_id):
    # Logic to delete a specific comment by its ID for a specific post
    post = get_object_or_404(Post, id=post_id)
    comment = get_object_or_404(Comment, id=comment_id)
    if request.user.profile.role == 'admin':
        if request.method == 'POST':
            post.comments.remove(comment)
            comment.delete()
            if notifications_enabled(comment.author.profile, 'receive_administration_notifications'):
                create_notice(
                    comment.author.profile,
                    f'Ваш комментарій к посту «{post.title}» видален адміністратором.',
                    'administration',
                )
            return redirect('post_detail', post_id=post.id)
        return render(request, 'core_posts/confirm_delete_comment.html', {'post': post, 'comment': comment})
    elif request.user == comment.author:
        if request.method == 'POST':
            post.comments.remove(comment)
            comment.delete()
            return redirect('post_detail', post_id=post.id)
        return render(request, 'core_posts/confirm_delete_comment.html', {'post': post, 'comment': comment})
    else:
        return redirect('home')


@login_required
def edit_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    post = get_object_or_404(Post, comments=comment)
    if request.method == 'POST':
        if request.user != comment.author and request.user.profile.role != 'admin':
            return redirect('home')
        else:
            form = CommentForm(request.POST, instance=comment)
            if form.is_valid():
                form.save()
                return redirect('post_detail', post_id=post.id)
    else:
        form = CommentForm(instance=comment)
    return render(request, 'core_posts/edit_comment.html', {'post': post, 'comment': comment, 'form': form})


@login_required
@require_POST
def react_to_post(request, post_id, reaction_type):
    # Try to get the object from Post model first, then News model
    try:
        post = get_object_or_404(Post, id=post_id)
    except Http404:
        post = get_object_or_404(News, id=post_id)

    if request.method == 'POST':
        valid_reactions = dict(Reaction.REACTION_CHOICES)
        if reaction_type not in valid_reactions:
            return JsonResponse({'error': 'Invalid reaction type.'}, status=400)

        # Check if the object supports reactions (Post model has reactions, News may not)
        if hasattr(post, 'reactions'):
            # Check if the user has already reacted to this post
            existing_reaction = post.reactions.filter(user=request.user).first()
            current_reaction = reaction_type
            if existing_reaction:
                # If the reaction type is the same, remove the reaction (toggle off)
                if existing_reaction.reaction_type == reaction_type:
                    existing_reaction.delete()
                    current_reaction = None
                else:
                    # Update the reaction type
                    existing_reaction.reaction_type = reaction_type
                    existing_reaction.save()
            else:
                # Create a new reaction
                post.reactions.create(user=request.user, reaction_type=reaction_type)
            # Aggregation for likes and dislikes
            reaction_counts = post.reactions.aggregate(
                like_count=Count('id', filter=Q(reaction_type='like')),
                dislike_count=Count('id', filter=Q(reaction_type='dislike'))
            )
            reaction = {
                'post_id': post.id,
                'likes': reaction_counts['like_count'],
                'dislikes': reaction_counts['dislike_count'],
                'user_id': request.user.id,
                'reaction_type': current_reaction,
            }
        else:
            # For objects that don't support reactions (like News without reactions field)
            # We'll still return a success response but without reaction counts
            reaction = {
                'post_id': post.id,
                'likes': 0,
                'dislikes': 0,
                'user_id': request.user.id,
                'reaction_type': reaction_type,
            }

        # Only send WebSocket update if the object has reactions
        if hasattr(post, 'reactions'):
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'post_reactions_{post.id}',
                {'type': 'reaction.update', 'reaction': reaction},
            )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse(reaction)
        # Redirect appropriately based on object type
        if isinstance(post, Post):
            return redirect('post_detail', post_id=post.id)
        else:  # News object
            return redirect('news_detail', news_id=post.id)
    return JsonResponse({'error': 'POST required.'}, status=405)


@login_required
def subscribe_to_user(request, user_id):
    if request.method == 'POST':
        user_to_follow = get_object_or_404(User, id=user_id)
        if user_to_follow == request.user:
            return JsonResponse({'error': 'You cannot follow yourself.'}, status=400)
        subscription, created = Subscription.objects.get_or_create(user=user_to_follow, follower=request.user)
        if not created:
            return JsonResponse({'error': 'You are already following this user.'}, status=400)
        if notifications_enabled(user_to_follow.profile, 'receive_subscription_notifications'):
            create_notice(
                user_to_follow.profile,
                f'{request.user.username} подписался на вас.',
                'subscription',
            )
        return JsonResponse({'message': f'You are now following {user_to_follow.username}.'})
    return JsonResponse({'error': 'POST required.'}, status=405)


@login_required
def all_subscriptions(request):
    subscriptions = Subscription.objects.filter(follower=request.user)
    return render(request, 'core_posts/all_subscriptions.html', {'subscriptions': subscriptions})


@login_required
def unsubscribe_from_user(request, user_id):
    if request.method == 'POST':
        user_to_unfollow = get_object_or_404(User, id=user_id)
        subscription = Subscription.objects.filter(user=user_to_unfollow, follower=request.user).first()
        if subscription:
            subscription.delete()
            return JsonResponse({'message': f'You have unsubscribed from {user_to_unfollow.username}.'})
        else:
            return JsonResponse({'error': 'You are not following this user.'}, status=400)
    return JsonResponse({'error': 'POST required.'}, status=405)


@login_required
def recommendation_for_user(request):

    # Get the current user's profile
    user_profile = request.user.profile

    # Get the friends of the current user
    friends = user_profile.friends.all()

    # Get the users tha
    # the current user is subscribed to
    subscriptions = Subscription.objects.filter(follower=request.user).values_list('user', flat=True)

    # Get posts from friends that the user hasn't commented on yet
    recommended_posts = Post.objects.filter(
        Q(author__profile__in=friends) |
        Q(author__profile__in=subscriptions)
    ).exclude(
        comments__author=request.user
    ).distinct().order_by('-created_at')

    # Note: file_kind is accessed via the property in the template, so no need to set it here

    return render(request, 'core_posts/ribbon.html', {
        'recommended_posts': recommended_posts,
    })


@login_required
def create_news(request):
    if request.user.profile.role != 'admin':
        return redirect('home')  # Redirect non-admin users to home or another page
    else:
        if request.method == 'POST':
            title = request.POST.get('title')
            content = request.POST.get('content')
            file = request.FILES.get('file')  # Get the uploaded file
            if title and content:
                news = News.objects.create(
                    title=title,
                    content=content,
                    file=file,
                    author=request.user,
                )
                return redirect('news_detail', news_id=news.id)
        return render(request, 'news/create_news.html')


@login_required
def edit_news(request, news_id):
    if request.user.profile.role != 'admin':
        return redirect('home')  # Redirect non-admin users to home or another page
    else:
        news = get_object_or_404(News, id=news_id)
        if request.method == 'POST':
            title = request.POST.get('title')
            content = request.POST.get('content')
            file = request.FILES.get('file')  # Get the uploaded file
            if title and content:
                news.title = title
                news.content = content
                if file:
                    news.file = file  # Update the file only if a new one is uploaded
                news.save()
                return redirect('news_detail', news_id=news.id)
        return render(request, 'news/edit_news.html', {'news': news})


@login_required
def delete_news(request, news_id):
    if request.user.profile.role != 'admin':
        return redirect('home')  # Redirect non-admin users to home or another page
    else:
        news = get_object_or_404(News, id=news_id)
        if request.method == 'POST':
            news.delete()
            return redirect('news_list')
        return render(request, 'news/confirm_delete_news.html', {'news': news})


def news_list(request):
    search_query = request.GET.get('q', '').strip()
    if search_query:
            news_items = News.objects.filter(
                Q(title__icontains=search_query)
                | Q(content__icontains=search_query)
                | Q(author__username__icontains=search_query)
            ).distinct().order_by('-created_at')
    else:
        news_items = News.objects.all().order_by('-created_at')

    return render(request, 'news/news_list.html', {'news_items': news_items, 'search_query': search_query})


def news_detail(request, news_id):
    news = get_object_or_404(News, id=news_id)
    file_kind = news.file_kind
    return render(request, 'news/news_detail.html', {'news': news, 'file_kind': file_kind})
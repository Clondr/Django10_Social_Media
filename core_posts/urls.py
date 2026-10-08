from django.urls import path
from . import views

urlpatterns = [
    path('post_list/', views.post_list, name='post_list'),
    path('post_detail/<int:post_id>/', views.post_detail, name='post_detail'),
    path('create_post/', views.create_post, name='create_post'),
    path('delete_post/<int:post_id>/', views.delete_post, name='delete_post'),
    path('delete_post_attachment/<int:post_id>/', views.delete_post_attachment, name='delete_post_attachment'),
    path('create_comment/<int:post_id>/', views.create_comment, name='create_comment'),
    path('delete_comment/<int:post_id>/<int:comment_id>/', views.delete_comment, name='delete_comment'),
    path('edit_post/<int:post_id>/', views.edit_post, name='edit_post'),
    path('edit_comment/<int:comment_id>/', views.edit_comment, name='edit_comment'),
    path('react/<int:post_id>/<str:reaction_type>/', views.react_to_post, name='react_to_post'),
    path('subscribe/<int:user_id>/', views.subscribe_to_user, name='subscribe_to_user'),
    path('subscriptions/', views.all_subscriptions, name='all_subscriptions'),
    path('unsubscribe/<int:user_id>/', views.unsubscribe_from_user, name='unsubscribe_from_user'),
    path('recommendations/', views.recommendation_for_user, name='recommendation_for_user'),
    path('news-list/', views.news_list, name='news_list'),
    path('news/detail/<int:news_id>/', views.news_detail, name='news_detail'),
    path('news/delete-attachment/<int:news_id>/', views.delete_news_attachment, name='delete_news_attachment'),
    path('news/create/', views.create_news, name='create_news'),
    path('news/edit/<int:news_id>/', views.edit_news, name='edit_news'),
    path('news/delete/<int:news_id>/', views.delete_news, name='delete_news'),
]
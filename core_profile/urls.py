from django.urls import path
from . import views


urlpatterns = [
    path('', views.profile_view, name='profile'),
    path('<int:id>/', views.profile_view, name='profile-view'),
    path('edit/', views.edit_profile_view, name='edit-profile'),
    path('delete_bio/', views.delete_bio_of_user, name='delete-bio'),
    path('change_settings/', views.change_settings, name='change-settings'),
]

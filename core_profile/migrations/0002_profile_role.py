from django.db import migrations, models


def assign_admin_role_to_superusers(apps, schema_editor):
    Profile = apps.get_model('core_profile', 'Profile')
    Profile.objects.filter(user__is_superuser=True).update(role='admin')


class Migration(migrations.Migration):

    dependencies = [
        ('core_profile', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='role',
            field=models.CharField(
                choices=[('user', 'User'), ('admin', 'Admin')],
                default='user',
                max_length=5,
            ),
        ),
        migrations.RunPython(
            assign_admin_role_to_superusers,
            migrations.RunPython.noop,
        ),
    ]

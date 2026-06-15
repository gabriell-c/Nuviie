from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0002_seed_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='financecategory',
            name='icon_svg',
            field=models.TextField(blank=True, default='', help_text='SVG inline opcional'),
        ),
    ]

from django.db import migrations


def seed_categories(apps, schema_editor):
    FinanceCategory = apps.get_model('finance', 'FinanceCategory')
    defaults = [
        ('Serviço Web', 'income', '#10b981', 'fa-globe'),
        ('Serviço Extra', 'income', '#06b6d4', 'fa-plus'),
        ('Assinatura / SaaS', 'expense', '#8b5cf6', 'fa-repeat'),
        ('Infraestrutura', 'expense', '#6366f1', 'fa-server'),
        ('Marketing', 'expense', '#f59e0b', 'fa-bullhorn'),
        ('Despesas Gerais', 'expense', '#ef4444', 'fa-arrow-down'),
    ]
    for name, ctype, color, icon in defaults:
        FinanceCategory.objects.get_or_create(
            name=name,
            category_type=ctype,
            defaults={'color': color, 'icon': icon},
        )


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]

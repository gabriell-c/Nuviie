# Generated migration for SiteAuditVisualAsset

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('site_audit', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteAuditVisualAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asset_id', models.CharField(db_index=True, max_length=32)),
                ('file', models.CharField(max_length=500)),
                ('kind', models.CharField(choices=[('crop', 'Crop'), ('screenshot', 'Screenshot')], default='crop', max_length=20)),
                ('audit_id', models.CharField(blank=True, max_length=120)),
                ('strategy', models.CharField(blank=True, max_length=20)),
                ('element_index', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='visual_assets', to='site_audit.siteauditreport')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='siteauditvisualasset',
            index=models.Index(fields=['expires_at'], name='site_audit__expires_6a8f2d_idx'),
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.9.6 on 2016-06-01 16:00
from __future__ import unicode_literals

from collections import defaultdict
from django.db import DEFAULT_DB_ALIAS, migrations, models, router
from django.apps import apps as live_apps


def de_dupe_version_table(apps, schema_editor):
    """
    Removes some duplicate Version models that may have crept into the database and will prevent the
    unique index being added by migration 0004.
    """
    db_alias = schema_editor.connection.alias
    Version = apps.get_model("reversion", "Version")
    keep_version_ids = Version.objects.using(db_alias).order_by().values_list(
        # Group by the unique constraint we intend to enforce.
        "revision_id",
        "content_type_id",
        "object_id",
    ).annotate(
        # Add in the most recent id for each duplicate row.
        max_pk=models.Max("pk"),
    ).values_list("max_pk", flat=True)

    print('keep_version_ids')
    print(keep_version_ids.query)
    # print(f'keep_version_ids.count(): {keep_version_ids.count()}')

    # Do not do anything if we're keeping all ids anyway.
    if keep_version_ids.count() == Version.objects.using(db_alias).all().count():
        return
    # Delete all duplicate versions. Can't do this as a delete with subquery because MySQL doesn't like running a
    # subquery on the table being updated/deleted.
    delete_version_ids = Version.objects.using(db_alias).exclude(
        pk__in=keep_version_ids,
    ).values_list("pk", flat=True)

    print(f'delete_version_ids: {delete_version_ids.count()}')

    Version.objects.using(db_alias).filter(
        pk__in=delete_version_ids,
    ).delete()


def set_version_db(apps, schema_editor):
    """
    Updates the db field in all Version models to point to the correct write
    db for the model.
    """
    db_alias = schema_editor.connection.alias
    Version = apps.get_model("reversion", "Version")
    content_types = Version.objects.using(db_alias).order_by().values_list(
        "content_type_id",
        "content_type__app_label",
        "content_type__model"
    ).distinct()

    print(f'len(content_types): {len(content_types)}')
    print(content_types.query)

    model_dbs = defaultdict(list)
    for content_type_id, app_label, model_name in content_types:
        # We need to be able to access all models in the project, and we can't
        # specify them up-front in the migration dependencies. So we have to
        # just get the live model. This should be fine, since we don't actually
        # manipulate the live model in any way.
        try:
            model = live_apps.get_model(app_label, model_name)
        except LookupError:
            # If the model appears not to exist, play it safe and use the default db.
            db = "default"
        else:
            db = router.db_for_write(model)
        model_dbs[db].append(content_type_id)
    # Update db field.
    # speedup for case when there is only default db
    if DEFAULT_DB_ALIAS in model_dbs and len(model_dbs) == 1:
        Version.objects.using(db_alias).update(db=DEFAULT_DB_ALIAS)
    else:
        for db, content_type_ids in model_dbs.items():
            Version.objects.using(db_alias).filter(
                content_type__in=content_type_ids
            ).update(db=db)


class Migration(migrations.Migration):

    dependencies = [
        ('reversion', '0002_auto_20141216_1509'),
    ]

    operations = [
        # migrations.RemoveField(
        #     model_name='revision',
        #     name='manager_slug',
        # ),
        # migrations.RemoveField(
        #     model_name='version',
        #     name='object_id_int',
        # ),
        # migrations.AlterField(
        #     model_name='version',
        #     name='object_id',
        #     field=models.TextField(help_text='Primary key of the model under version control.'),
        # ),
        # migrations.AlterField(
        #     model_name='revision',
        #     name='date_created',
        #     field=models.DateTimeField(db_index=True, help_text='The date and time this revision was created.', verbose_name='date created'),
        # ),
        # migrations.AddField(
        #     model_name='version',
        #     name='db',
        #     field=models.TextField(null=True, help_text='The database the model under version control is stored in.'),
        # ),
#         migrations.RunSQL("""
#         BEGIN;
# --
# -- Remove field manager_slug from revision
# --
# ALTER TABLE "reversion_revision" DROP COLUMN "manager_slug";
# --
# -- Remove field object_id_int from version
# --
# ALTER TABLE "reversion_version" DROP COLUMN "object_id_int";
# --
# -- Alter field object_id on version
# --
# --
# -- Alter field date_created on revision
# --
# --
# -- Add field db to version
# --
# ALTER TABLE "reversion_version" ADD COLUMN "db" text NULL;
# --
# -- MIGRATION NOW PERFORMS OPERATION THAT CANNOT BE WRITTEN AS SQL:
# -- Raw Python operation
# --
# --
# -- MIGRATION NOW PERFORMS OPERATION THAT CANNOT BE WRITTEN AS SQL:
# -- Raw Python operation
# --
# COMMIT;
#         """),
        migrations.RunPython(de_dupe_version_table),
        migrations.RunPython(set_version_db),
    ]

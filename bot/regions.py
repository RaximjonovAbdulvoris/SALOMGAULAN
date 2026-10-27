"""Internal routing adapter for one SALOM park. No region choice or fallback."""
from bot.route_settings import destination

PARK = 'salom'


def get_region(context):
    return PARK


def region_name(region):
    return 'WB SALOM'


def clear_application(context):
    context.user_data.clear()


def driver_groups(region=PARK):
    if region != PARK:
        return []
    return [value for i in (1, 2) if (value := destination(f'DRIVER_GROUP_{i}'))]


def application_group(region, kind):
    return destination({'brand': 'BRAND_GROUP', 'spectre': 'SPECTRE_GROUP'}[kind]) if region == PARK and kind in ('brand', 'spectre') else ''


def archive_group(region=PARK):
    return destination('ARCHIVE_GROUP') if region == PARK else ''

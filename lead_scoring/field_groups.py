"""Atribui grupo (general/instagram/google_maps) a cada campo do registro."""

INSTAGRAM_PATHS = {
    'effective_post_count', 'amenities.follower_count', 'amenities.post_count',
    'amenities.latest_post_at', 'days_since_latest_post',
    'amenities.recent_posts', 'amenities.recent_reels', 'is_verified',
}

GOOGLE_MAPS_PATHS = {
    'address', 'rating', 'review_count', 'recent_reviews', 'recent_reviews_count',
    'business_hours', 'maps_url', 'maps_share_url', 'price_range', 'plus_code',
    'amenities', 'total_photos',
}


def field_group_for_path(path: str) -> str:
    if path in INSTAGRAM_PATHS:
        return 'instagram'
    if path in GOOGLE_MAPS_PATHS:
        return 'google_maps'
    return 'general'

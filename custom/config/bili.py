CONFIG = {
    # keyword
    "platform": "bili",
    "keyword_table": "bilibili_video",
    "keyword_field": "source_keyword",
    "keyword_update_field": "last_modify_ts",

    # creator
    "source_table": "bilibili_video",
    "source_user_id_field": "user_id",

    "target_table": "bilibili_up_info",
    "target_user_id_field": "user_id",
    "target_update_field": "last_modify_ts",

    # command
    "batch_size": 500,

    "sleep_min": 600,
    "sleep_max": 900,

    "cmd_args": [
        "--lt", "qrcode",
        "--crawler_max_notes_count", "50",
        "--get_comment", "True",
        "--get_sub_comment", "True",
        "--max_comments_count_singlenotes", "50",
    ]
}
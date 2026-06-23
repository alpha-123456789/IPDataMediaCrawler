CONFIG = {
    # keyword
    "platform": "xhs",
    "keyword_table": "xhs_note",
    "keyword_field": "source_keyword",
    "keyword_update_field": "last_update_time",

    # creator
    "source_table": "xhs_note",
    "source_user_id_field": "user_id",

    "target_table": "xhs_creator",
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
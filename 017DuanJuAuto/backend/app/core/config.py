import os


def get_config_path():
    user_dir = os.path.join(os.path.expanduser("~"), ".017DuanJuAuto")
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
    return user_dir


import os

import yaml

CONFIG_DIR_PATH = os.path.expanduser('~/.jetere')
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR_PATH, 'config.yaml')


class _Config(dict):
    def __init__(self):
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r') as f:
                self.update(yaml.load(f))

instance = _Config()

import os, yaml
DEFAULTS = {'db': '/var/lib/thilek/thilek.db', 'data_root': '/var/lib/thilek/data', 'admin_password': ''}
def load():
    path = os.environ.get('THILEK_CONFIG', '/etc/thilek/config.yaml')
    cfg = dict(DEFAULTS)
    if os.path.isfile(path):
        cfg.update(yaml.safe_load(open(path, encoding='utf-8')) or {})
    for k, env in (('db', 'THILEK_DB'), ('data_root', 'THILEK_ROOT'), ('admin_password', 'THILEK_PASSWORD')):
        if os.environ.get(env): cfg[k] = os.environ[env]
    return cfg

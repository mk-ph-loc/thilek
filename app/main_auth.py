import secrets
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from . import config
basic = HTTPBasic(auto_error=False)

def auth(cred: HTTPBasicCredentials | None = Depends(basic)):
    pw = config.load()['admin_password']
    if not pw: return                      # χωρίς κωδικό (μόνο για ανάπτυξη)
    if not cred or not secrets.compare_digest(cred.password.encode(), pw.encode()):
        raise HTTPException(401, headers={'WWW-Authenticate': 'Basic'})

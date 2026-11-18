"""Generate private, per-machine demo signing/knowledge keys in ignored logs."""
import argparse
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def private_file(path, content):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        stream.write(content)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix',default='showcase-local')
    args=parser.parse_args()
    if not args.prefix.replace('-','').replace('_','').isalnum(): parser.error('Use a simple local filename prefix')
    folder=Path(__file__).resolve().parents[1]/'logs'
    folder.mkdir(exist_ok=True)
    key_path=folder/(args.prefix+'-rs256.key')
    env_path=folder/(args.prefix+'-settings.env')
    if key_path.exists() or env_path.exists(): parser.error('Files already exist; reuse them or choose a new prefix')
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode('ascii')
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
    private_file(key_path,json.dumps([{'kid':'demo-'+uuid4().hex,'status':'active','private_pem':private,'public_pem':public}],indent=2)+'\n')
    private_file(env_path,'# Copy these settings into this machine\'s ignored .env.\n'
        'EMPLOYEE_IDENTITY_MODE=base_rs256\nBASE_PORTAL_ORIGIN=http://127.0.0.1:5193\nBASE_LOCAL_INSECURE_COOKIES=true\n'
        f'BASE_JWT_KEYS_FILE="{key_path.as_posix()}"\nSTU_ASSISTANT_MODE=workspace\n'
        f'STU_KNOWLEDGE_TOKEN={secrets.token_urlsafe(32)}\n')
    print('Private signing key: '+str(key_path))
    print('Copy settings from: '+str(env_path))


if __name__=='__main__': main()
